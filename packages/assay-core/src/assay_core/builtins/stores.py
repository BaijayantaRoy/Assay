"""Built-in stores (``assay.stores``).

The file store is canonical: prompts are files in a git repository, and git is the
version history. Everything else — SQL, S3, a remote registry — implements the same
five methods and can be swapped in without any caller noticing.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable

from ..contracts import CONTRACT_VERSION
from ..errors import NotFound, StoreError, ValidationError
from ..promptfile import PromptFile, discover


PROMPT_ID_RE = re.compile(
    r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?"
    r"(/[a-z0-9]([a-z0-9._-]*[a-z0-9])?)*$"
)


class FileStore:
    """Git-native store over a directory of PromptFiles.

    ``version`` lookups resolve against git history when the working tree is a repo,
    which is what makes ``assay get support/triage@3`` work with no database.
    """

    id = "file"
    contract_version = CONTRACT_VERSION

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()
        self._index: dict[str, Path] | None = None

    # -- indexing ----------------------------------------------------------

    def reindex(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        for path in discover(self.root):
            try:
                pf = PromptFile.load(path)
            except Exception:
                continue  # a broken file must not take down discovery
            if pf.id:
                index[pf.id] = path
        self._index = index
        return index

    @property
    def index(self) -> dict[str, Path]:
        if self._index is None:
            self.reindex()
        # Must return the live mapping, not a copy — an empty index is still the index,
        # and callers mutate it after a put().
        return self._index if self._index is not None else {}

    def path_for(self, prompt_id: str) -> Path:
        self._validate_id(prompt_id)
        if prompt_id in self.index:
            return self._contained(self.index[prompt_id])
        return self._contained(self.root / f"{prompt_id}.prompt.md")

    # -- Store contract ----------------------------------------------------

    def list(self, *, prefix: str | None = None) -> Iterable[str]:
        # Refresh so a long-lived MCP/API process sees files written by another process.
        self.reindex()
        ids = sorted(self.index)
        return [i for i in ids if i.startswith(prefix)] if prefix else ids

    def get(self, prompt_id: str, *, version: int | None = None) -> PromptFile:
        self._validate_id(prompt_id)
        path = self.index.get(prompt_id)
        if path is None:
            self.reindex()
            path = self.index.get(prompt_id)
        if path is None:
            raise NotFound(f"No prompt with id {prompt_id!r}", prompt_id=prompt_id,
                           available=sorted(self.index)[:20])
        if version is None:
            return PromptFile.load(path)
        return self._at_version(prompt_id, path, version)

    def put(self, prompt: PromptFile, *, message: str | None = None) -> PromptFile:
        if not prompt.id:
            raise StoreError("PromptFile has no 'id'; cannot store it")
        self._validate_id(prompt.id)
        problems = prompt.validate()
        if problems:
            raise ValidationError(
                f"PromptFile {prompt.id!r} does not conform to the specification",
                errors=problems,
                prompt_id=prompt.id,
            )
        target = self._contained(prompt.path) if prompt.path else self.path_for(prompt.id)
        prompt.save(target)
        self.index[prompt.id] = target
        if message and self._is_repo():
            self._git("add", str(target))
            self._git("commit", "-m", message, "--", str(target))
        return prompt

    def delete(self, prompt_id: str) -> None:
        self._validate_id(prompt_id)
        path = self.index.get(prompt_id)
        if path is None:
            raise NotFound(f"No prompt with id {prompt_id!r}", prompt_id=prompt_id)
        self._contained(path).unlink(missing_ok=True)
        self.index.pop(prompt_id, None)

    def _validate_id(self, prompt_id: str) -> None:
        if len(prompt_id) > 512 or not PROMPT_ID_RE.fullmatch(prompt_id):
            raise StoreError(
                "Invalid PromptFile id; use lowercase path segments without empty, dot, "
                "or traversal segments",
                prompt_id=prompt_id,
            )

    def _contained(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise StoreError(
                "PromptFile path escapes the configured store root",
                path=str(resolved), root=str(self.root),
            ) from exc
        return resolved

    def history(self, prompt_id: str) -> list[dict]:
        """Git log for the file backing this prompt. Empty list outside a repo."""
        path = self.index.get(prompt_id)
        if path is None:
            raise NotFound(f"No prompt with id {prompt_id!r}", prompt_id=prompt_id)
        if not self._is_repo():
            return []
        out = self._git(
            "log", "--follow", "--format=%H%x1f%an%x1f%aI%x1f%s", "--", str(path)
        )
        entries = []
        for line in (out or "").splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                entries.append({
                    "commit": parts[0], "author": parts[1],
                    "date": parts[2], "message": parts[3],
                })
        return entries

    # -- git helpers -------------------------------------------------------

    def _at_version(self, prompt_id: str, path: Path, version: int) -> PromptFile:
        current = PromptFile.load(path)
        if current.version == version:
            return current
        for entry in self.history(prompt_id):
            blob = self._git("show", f"{entry['commit']}:{self._rel(path)}")
            if blob is None:
                continue
            try:
                candidate = PromptFile.parse(blob, path=path)
            except Exception:
                continue
            if candidate.version == version:
                return candidate
        raise NotFound(
            f"Version {version} of {prompt_id!r} not found in history",
            prompt_id=prompt_id, version=version, current=current.version,
        )

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._repo_root() or self.root)).replace("\\", "/")
        except ValueError:
            return str(path)

    def _repo_root(self) -> Path | None:
        out = self._git("rev-parse", "--show-toplevel")
        return Path(out.strip()) if out else None

    def _is_repo(self) -> bool:
        return self._git("rev-parse", "--is-inside-work-tree") is not None

    def _git(self, *args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args], cwd=self.root, capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout if result.returncode == 0 else None


class MemoryStore:
    """In-process store. Used by tests and by the MCP server's ephemeral mode."""

    id = "memory"
    contract_version = CONTRACT_VERSION

    def __init__(self) -> None:
        self._data: dict[str, PromptFile] = {}
        self._log: dict[str, list[dict]] = {}

    def list(self, *, prefix: str | None = None) -> Iterable[str]:
        ids = sorted(self._data)
        return [i for i in ids if i.startswith(prefix)] if prefix else ids

    def get(self, prompt_id: str, *, version: int | None = None) -> PromptFile:
        if prompt_id not in self._data:
            raise NotFound(f"No prompt with id {prompt_id!r}", prompt_id=prompt_id)
        return self._data[prompt_id]

    def put(self, prompt: PromptFile, *, message: str | None = None) -> PromptFile:
        self._data[prompt.id] = prompt
        self._log.setdefault(prompt.id, []).append(
            {"version": prompt.version, "message": message or ""}
        )
        return prompt

    def delete(self, prompt_id: str) -> None:
        self._data.pop(prompt_id, None)

    def history(self, prompt_id: str) -> list[dict]:
        return list(self._log.get(prompt_id, []))

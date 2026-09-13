"""PromptFile v1 — parse, validate, serialize.

The document model is an ordered ``dict`` plus a body string. Unknown keys are kept
in that dict and written back verbatim, which is what makes round-tripping lossless
and forward compatibility real rather than aspirational.

See ``spec/promptfile-v1.md`` for the normative specification.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .errors import ParseError, UnsupportedSpecVersion, ValidationError

SPEC_MAJOR = 1
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n(.*))?$", re.DOTALL)

#: Canonical key order for serialization. Keys not listed keep their original
#: relative order and are appended after the known ones.
KEY_ORDER = [
    "promptfile", "id", "name", "summary", "description", "version", "kind", "status", "tags", "labels",
    "authors", "license", "requires", "engine", "input", "output", "model", "messages",
    "harness", "loop", "calibration", "governance", "tools", "attachments", "includes", "evals", "guardrails",
    "provenance", "deprecation",
]

#: Kinds that are composed into other prompts rather than executed directly. They are
#: exempt from the "stable prompts need evals" rule.
NON_EXECUTABLE_KINDS = frozenset({"system", "fragment", "snippet", "partial"})

#: Assertion types that inspect *how* the agent worked rather than what it produced.
#: A stable harness asserting only on output is flagged by the linter, because that is
#: the review gap through which agent regressions actually arrive.
_TRAJECTORY_ASSERTIONS = frozenset({
    "tool_called", "tool_not_called", "tool_call_order", "trajectory_accuracy",
    "no_repeated_tool_call",
    "iterations_under", "tool_calls_under", "budget_under", "no_tool_errors",
    "no_denied_calls", "completed", "verified", "cycles_under", "goal_met",
    "no_injection_compliance", "injection_detected", "memory_recalled", "memory_written",
    "steps_verified",
})

_SCHEMA_CACHE: dict[int, dict] = {}


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_UniqueKeyLoader)


def _jsonify(value: Any) -> Any:
    """Coerce YAML-native scalars into their JSON equivalents for validation.

    PyYAML resolves an unquoted ``2026-07-27T00:00:00Z`` into a ``datetime``, which then
    fails a ``type: string`` check even though the file on disk is perfectly valid. We
    normalise for *validation only* — ``self.data`` keeps the original objects so
    round-tripping stays lossless.
    """
    import datetime as _dt

    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    return value


def _schema_path(major: int) -> Path:
    here = Path(__file__).resolve()
    # packages/assay-core/src/assay_core/promptfile.py -> repo root
    for parent in here.parents:
        candidate = parent / "spec" / "schemas" / f"promptfile-v{major}.schema.json"
        if candidate.exists():
            return candidate
    bundled = here.parent / "schemas" / f"promptfile-v{major}.schema.json"
    if bundled.exists():
        return bundled
    raise ValidationError(f"PromptFile schema v{major} not found on disk")


def load_schema(major: int = SPEC_MAJOR) -> dict:
    if major not in _SCHEMA_CACHE:
        _SCHEMA_CACHE[major] = json.loads(_schema_path(major).read_text(encoding="utf-8"))
    return _SCHEMA_CACHE[major]


class _OrderedDumper(yaml.SafeDumper):
    """Dumper that keeps insertion order and emits readable block strings."""


def _str_representer(dumper: yaml.SafeDumper, data: str):
    # YAML normalises CR, NEL, line-separator, and paragraph-separator characters
    # when they are emitted as plain/block scalars.  Double-quoted scalars make
    # PyYAML escape them (\r, \N, \L, \P), preserving future/unknown JSON values
    # exactly across a YAML or frontmatter round trip.
    if any(char in data for char in ("\r", "\x85", "\u2028", "\u2029")):
        style = '"'
    else:
        style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_OrderedDumper.add_representer(str, _str_representer)


@dataclass
class PromptFile:
    """An in-memory PromptFile.

    ``data`` holds the frontmatter exactly as parsed, including any keys this build
    does not understand. ``body`` holds the markdown body (or the ``body:`` key for
    pure-YAML files).
    """

    data: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    path: Path | None = None
    source_format: str = "md"  # md | yaml | json

    # -- convenience accessors --------------------------------------------

    @property
    def id(self) -> str:
        return self.data.get("id", "")

    @property
    def name(self) -> str:
        return self.data.get("name") or self.id.rsplit("/", 1)[-1]

    @property
    def version(self) -> int:
        return int(self.data.get("version", 1))

    @property
    def kind(self) -> str:
        return self.data.get("kind", "prompt")

    @property
    def status(self) -> str:
        return self.data.get("status", "draft")

    @property
    def tags(self) -> list[str]:
        return list(self.data.get("tags", []))

    @property
    def engine(self) -> dict:
        return dict(self.data.get("engine") or {})

    @property
    def renderer_id(self) -> str:
        return self.engine.get("template", "jinja2")

    @property
    def strict(self) -> bool:
        return bool(self.engine.get("strict", True))

    @property
    def model_ref(self) -> str | None:
        return (self.data.get("model") or {}).get("primary")

    @property
    def fallbacks(self) -> list[str]:
        return list((self.data.get("model") or {}).get("fallbacks", []))

    @property
    def params(self) -> dict:
        return dict((self.data.get("model") or {}).get("params", {}))

    @property
    def provider_params(self) -> dict:
        return dict((self.data.get("model") or {}).get("provider_params", {}))

    @property
    def messages(self) -> list[dict]:
        msgs = self.data.get("messages")
        if msgs:
            return [dict(m) for m in msgs]
        return [{"role": "user", "content": self.body}]

    @property
    def input_schema(self) -> dict | None:
        return (self.data.get("input") or {}).get("schema")

    @property
    def output_schema(self) -> dict | None:
        return (self.data.get("output") or {}).get("schema")

    @property
    def required_capabilities(self) -> frozenset[str]:
        return frozenset((self.data.get("requires") or {}).get("capabilities", []))

    @property
    def evals(self) -> list[dict]:
        return list(self.data.get("evals") or [])

    @property
    def guardrails(self) -> list[dict]:
        return list(self.data.get("guardrails") or [])

    @property
    def extensions(self) -> dict[str, Any]:
        """All ``x-`` namespaced keys — preserved but not interpreted by core."""
        return {k: v for k, v in self.data.items() if k.startswith("x-")}

    # -- harness / loop ----------------------------------------------------

    @property
    def harness(self) -> dict:
        return dict(self.data.get("harness") or {})

    @property
    def loop(self) -> dict:
        return dict(self.data.get("loop") or {})

    @property
    def tools(self) -> list[dict]:
        return list(self.data.get("tools") or [])

    @property
    def is_harness(self) -> bool:
        return self.kind in ("harness", "agent") and bool(self.data.get("harness"))

    @property
    def is_loop(self) -> bool:
        return self.kind == "loop" and bool(self.data.get("loop"))

    @property
    def is_agentic(self) -> bool:
        """True when this artifact executes a loop rather than a single model call."""
        return self.is_harness or self.is_loop

    # -- parsing -----------------------------------------------------------

    @classmethod
    def parse(cls, text: str, *, path: Path | None = None, fmt: str | None = None) -> "PromptFile":
        """Parse markdown-with-frontmatter, YAML, or JSON into a PromptFile."""
        fmt = fmt or cls._sniff(text, path)
        if fmt == "json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ParseError(f"Invalid JSON: {exc}", path=str(path) if path else None) from exc
            body = data.pop("body", "") or ""
        elif fmt == "yaml":
            try:
                data = _load_yaml(text) or {}
            except yaml.YAMLError as exc:
                raise ParseError(f"Invalid YAML: {exc}") from exc
            if not isinstance(data, dict):
                raise ParseError("Top level of a .prompt.yaml must be a mapping")
            body = data.pop("body", "") or ""
        else:
            match = FRONTMATTER_RE.match(text.lstrip("﻿"))
            if not match:
                raise ParseError(
                    "Missing YAML frontmatter. A .prompt.md file must start with '---'.",
                    path=str(path) if path else None,
                )
            try:
                data = _load_yaml(match.group(1)) or {}
            except yaml.YAMLError as exc:
                raise ParseError(f"Invalid YAML frontmatter: {exc}") from exc
            if not isinstance(data, dict):
                raise ParseError("Frontmatter must be a YAML mapping")
            body = (match.group(2) or "").strip("\n")

        pf = cls(data=data, body=body, path=path, source_format=fmt)
        pf.check_spec_version()
        return pf

    @classmethod
    def load(cls, path: str | Path) -> "PromptFile":
        p = Path(path)
        return cls.parse(p.read_text(encoding="utf-8"), path=p)

    @staticmethod
    def _sniff(text: str, path: Path | None) -> str:
        if path:
            suffix = path.suffix.lower()
            if suffix == ".json":
                return "json"
            if suffix in {".yaml", ".yml"}:
                return "yaml"
            if suffix in {".md", ".markdown"}:
                return "md"
        stripped = text.lstrip()
        if stripped.startswith("{"):
            return "json"
        if stripped.startswith("---"):
            return "md"
        return "yaml"

    def check_spec_version(self) -> None:
        raw = self.data.get("promptfile")
        if raw is None:
            raise ValidationError(
                "Missing required 'promptfile:' spec version key",
                errors=["promptfile: required"],
                path=str(self.path) if self.path else None,
            )
        try:
            major = int(str(raw).split(".", 1)[0])
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"'promptfile' must be an integer, got {raw!r}") from exc
        if major != SPEC_MAJOR:
            raise UnsupportedSpecVersion(
                f"This build implements PromptFile v{SPEC_MAJOR}; file declares v{major}. "
                f"Upgrade assay-core; no automated migration is available for PromptFile v{major}.",
                file_version=major, supported=SPEC_MAJOR,
                path=str(self.path) if self.path else None,
            )

    # -- validation --------------------------------------------------------

    def validate(self, *, strict: bool = False) -> list[str]:
        """Validate against the JSON Schema. Returns a list of human-readable errors.

        ``strict=True`` additionally reports lint-level problems: undeclared template
        variables, missing required metadata, unknown plugin references.
        """
        import jsonschema

        payload = _jsonify(dict(self.data))
        if self.body:
            payload.setdefault("body", self.body)

        errors: list[str] = []
        validator = jsonschema.Draft202012Validator(load_schema(SPEC_MAJOR))
        for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
            location = "/".join(str(p) for p in err.path) or "<root>"
            errors.append(f"{location}: {err.message}")

        if strict:
            errors.extend(self._lint())
        return errors

    def _lint(self) -> list[str]:
        problems: list[str] = []
        if not self.data.get("name"):
            problems.append("<root>: 'name' is recommended for discoverability")
        if not self.data.get("description"):
            problems.append("<root>: 'description' is recommended for discoverability")
        # Fragments are composed into other prompts rather than executed on their own,
        # so demanding eval cases from them is noise, not rigour.
        if self.status == "stable" and not self.evals and self.kind not in NON_EXECUTABLE_KINDS:
            problems.append("evals: a 'stable' prompt should carry at least one eval case")

        try:
            used = self.template_variables()
        except Exception as exc:  # noqa: BLE001 - third-party renderer boundary
            problems.append(f"engine.template: invalid template: {exc}")
            used = set()
        declared = set((self.input_schema or {}).get("properties", {}))
        if declared:
            for missing in sorted(used - declared):
                problems.append(f"input.schema: template uses '{{{{{missing}}}}}' but it is not declared")
        if self.data.get("deprecation") and self.status != "deprecated":
            problems.append("status: 'deprecation' block present but status is not 'deprecated'")
        problems.extend(self._lint_disclosure())
        problems.extend(self._lint_agentic())
        return problems

    def _lint_disclosure(self) -> list[str]:
        """Tier-1 discoverability.

        A prompt's one-line summary is what every client sees before deciding whether to
        load it. Too long and it eats the shared index budget; missing and the prompt is
        effectively invisible in a large library.
        """
        from .disclosure import MAX_SUMMARY_CHARS

        problems: list[str] = []
        summary = self.data.get("summary") or self.data.get("description") or ""
        if summary and len(summary) > MAX_SUMMARY_CHARS:
            problems.append(
                f"description: {len(summary)} chars exceeds the tier-1 index budget of "
                f"{MAX_SUMMARY_CHARS}. Add a short 'summary:' field, or shorten it — this "
                "text is loaded for every client on every listing"
            )
        return problems

    def _lint_agentic(self) -> list[str]:
        """Checks specific to harnesses and loops.

        These catch the failures that make agents expensive or unsafe, and they are
        exactly the ones invisible in a normal prompt review.
        """
        problems: list[str] = []

        if self.is_harness:
            harness = self.harness
            budget = harness.get("budget") or {}
            if not budget:
                problems.append(
                    "harness.budget: no budget set — an agent loop without a cost, token or "
                    "wallclock ceiling is an unbounded spend"
                )
            if not harness.get("max_iterations") and not budget.get("iterations"):
                problems.append(
                    "harness.max_iterations: not set; the runtime default will be used"
                )
            if not self.tools:
                problems.append(
                    "tools: a harness with no tools is a prompt — consider kind: prompt"
                )
            control = harness.get("control") or {}
            if control.get("allow_shell") and not control.get("allow_commands"):
                problems.append(
                    "harness.control: allow_shell is true with no allow_commands allow list; "
                    "the agent can run any command in the sandbox"
                )
            if not control.get("max_repeated_calls"):
                problems.append(
                    "harness.control.max_repeated_calls: not set; nothing stops the agent "
                    "repeating an identical tool call indefinitely"
                )
            if self.status == "stable":
                asserted = {
                    a.get("type")
                    for case in self.evals for a in (case.get("assert") or [])
                }
                if asserted and not asserted & _TRAJECTORY_ASSERTIONS:
                    problems.append(
                        "evals: this harness only asserts on final output. Add a trajectory "
                        "assertion (tool_called, iterations_under, no_repeated_tool_call, "
                        "budget_under) — most agent regressions are invisible in the output"
                    )

        if self.is_loop:
            loop = self.loop
            if not loop.get("verify"):
                problems.append(
                    "loop.verify: no verification step — the agent marks its own homework. "
                    "Add a command-based check whose exit code decides success"
                )
            if not loop.get("budget") and not loop.get("max_cycles"):
                problems.append(
                    "loop.budget: neither budget nor max_cycles set — this loop can run away"
                )
            if not loop.get("steps"):
                problems.append("loop.steps: a loop with no steps does nothing")
            verify = loop.get("verify") or {}
            if verify.get("run") and not verify.get("command"):
                problems.append(
                    "loop.verify: model-graded verification only. A model grading a model is "
                    "a weak signal; prefer a command whose exit code is the verdict"
                )
        return problems

    def template_variables(self) -> set[str]:
        """Union of variables referenced across body and all messages."""
        from .registry import get_registry

        try:
            renderer = get_registry().get("assay.renderers", self.renderer_id)
        except Exception:
            renderer = get_registry().get("assay.renderers", "jinja2")
        found: set[str] = set()
        for msg in self.messages:
            content = msg.get("content")
            if isinstance(content, str):
                found |= renderer.variables_of(content)
        if self.body:
            found |= renderer.variables_of(self.body)
        return found

    # -- serialization -----------------------------------------------------

    def to_text(self, *, fmt: str | None = None) -> str:
        """Serialize. Unknown keys are preserved; ``promptfile`` is always emitted first."""
        fmt = fmt or self.source_format
        ordered = self._ordered_data()

        if fmt == "json":
            payload = dict(ordered)
            if self.body:
                payload["body"] = self.body
            return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

        if fmt == "yaml":
            payload = dict(ordered)
            if self.body:
                payload["body"] = self.body
            return yaml.dump(
                payload, Dumper=_OrderedDumper, sort_keys=False,
                allow_unicode=True, default_flow_style=False, width=100,
            )

        front = yaml.dump(
            ordered, Dumper=_OrderedDumper, sort_keys=False,
            allow_unicode=True, default_flow_style=False, width=100,
        )
        return f"---\n{front}---\n\n{self.body}\n" if self.body else f"---\n{front}---\n"

    def _ordered_data(self) -> dict[str, Any]:
        known = [k for k in KEY_ORDER if k in self.data]
        rest = [k for k in self.data if k not in KEY_ORDER]
        return {k: self.data[k] for k in known + rest}

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise ParseError("No path to save to; pass one explicitly")
        target = target.resolve(strict=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        fmt = "md"
        if target.suffix.lower() == ".json":
            fmt = "json"
        elif target.suffix.lower() in {".yaml", ".yml"}:
            fmt = "yaml"
        content = self.to_text(fmt=fmt)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", delete=False,
                dir=target.parent, prefix=f".{target.name}.", suffix=".tmp",
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink(missing_ok=True)
        self.path = target
        return target

    def bump(self, *, message: str | None = None) -> int:
        """Increment the revision counter and stamp provenance."""
        from datetime import datetime, timezone

        self.data["version"] = self.version + 1
        prov = dict(self.data.get("provenance") or {})
        prov["updated_at"] = datetime.now(timezone.utc).isoformat()
        if message:
            prov["message"] = message
        self.data["provenance"] = prov
        return self.data["version"]

    def to_dict(self) -> dict:
        d = dict(self._ordered_data())
        if self.body:
            d["body"] = self.body
        return d

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<PromptFile {self.id}@{self.version} kind={self.kind}>"


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

PROMPT_GLOBS = ("**/*.prompt.md", "**/*.prompt.yaml", "**/*.prompt.yml", "**/*.prompt.json")
PROMPT_SUFFIXES = (".prompt.md", ".prompt.yaml", ".prompt.yml", ".prompt.json")

#: Directories never worth descending into. Pruned *during* the walk rather than
#: filtered afterwards — globbing a repository that contains node_modules or a
#: virtualenv and discarding the matches later costs seconds per invocation.
IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env", "__pycache__",
    ".next", ".nuxt", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "site-packages", ".terraform", "target", "vendor",
}


def discover(
    root: str | Path,
    *,
    globs: Iterable[str] | None = None,
    ignore: Iterable[str] | None = None,
) -> list[Path]:
    """Find every PromptFile under ``root``.

    ``globs`` is accepted for backward compatibility; when omitted the faster
    pruned walk is used, which is equivalent for the default patterns.
    """
    base = Path(root)
    if not base.exists():
        return []
    if base.is_file():
        return [base] if base.name.endswith(PROMPT_SUFFIXES) else []

    ignored = IGNORED_DIRS | set(ignore or ())

    if globs is not None and tuple(globs) != PROMPT_GLOBS:
        found = [
            p for pattern in globs for p in base.glob(pattern)
            if not any(part in ignored for part in p.parts)
        ]
        return sorted(set(found))

    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        # Mutating dirnames in place is what prunes the walk.
        dirnames[:] = [d for d in dirnames if d not in ignored and not d.startswith(".")]
        for filename in filenames:
            if filename.endswith(PROMPT_SUFFIXES):
                found.append(Path(dirpath) / filename)
    return sorted(found)

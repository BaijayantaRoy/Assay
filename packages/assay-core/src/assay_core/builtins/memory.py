"""Built-in memory backends (``assay.memory``).

Recall strategy
---------------
Recall is **hybrid**, because each signal alone fails in a characteristic way:

* **Keyword overlap** finds topically related records but misses exact identifiers.
* **Entity match** finds records about *this file, this ticket, this function* — which
  is usually what stops an agent redoing work — but misses paraphrase.
* **Recency** keeps memory current, but on its own degrades to a transcript.
* **Outcome weighting** surfaces failures preferentially, because "this approach did not
  work" is worth more per token than "this worked".

The default backend deliberately uses no embeddings. Vector similarity is a genuine
improvement for paraphrase, but it adds a model dependency to a component that must work
offline, and it is *worse* than keyword match at exact identifiers. A vector backend is a
plugin; this one is the floor, and the floor should have no dependencies.

Storage
-------
JSONL under ``.assay/memory/<namespace>.jsonl`` — append-only, greppable, diffable, and
deletable with an editor. Memory a user cannot inspect is memory a user cannot trust.
"""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..contracts import CONTRACT_VERSION, MemoryRecord

#: Words carrying no discriminative signal for recall.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those is are was were be been being
of to in on at by for with from as it its into about over under again further once
i you he she we they what which who whom do does did doing have has had having will
would should could can may might must not no nor own same so too very just now
""".split())

_WORD = re.compile(r"[a-z0-9_][a-z0-9_.\-/]*", re.IGNORECASE)
#: Identifier-shaped tokens: paths, dotted names, snake/camel case, ticket ids.
_ENTITY = re.compile(
    r"\b(?:[\w-]+/[\w./-]+"          # paths and namespaced ids
    r"|[A-Za-z_][\w]*\.[A-Za-z_][\w.]*"  # dotted names
    r"|[A-Z]{2,}-\d+"                 # TICKET-123
    r"|\w+\.(?:py|ts|tsx|js|md|json|yaml|yml|toml|sql|go|rs|java))\b"
)

_HALF_LIFE_DAYS = 30.0


def tokenize(text: str) -> set[str]:
    return {
        w.lower() for w in _WORD.findall(text or "")
        if len(w) > 2 and w.lower() not in _STOPWORDS
    }


def extract_entities(text: str, limit: int = 25) -> list[str]:
    """Pull identifier-shaped tokens out of free text.

    Cheap and imperfect. Its value is that exact identifiers are what an agent needs to
    match on, and embeddings are bad at them.
    """
    seen: list[str] = []
    for match in _ENTITY.findall(text or ""):
        if match not in seen:
            seen.append(match)
        if len(seen) >= limit:
            break
    return seen


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_days(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400)
    except Exception:
        return 0.0


class JsonlMemory:
    """File-backed memory with hybrid recall. The default backend."""

    id = "jsonl"
    contract_version = CONTRACT_VERSION

    #: Relative contribution of each signal. Entity match is weighted highest because an
    #: exact identifier hit is the strongest evidence that a record is about *this* task.
    WEIGHTS = {"entity": 3.0, "keyword": 2.0, "recency": 1.0, "outcome": 0.75, "semantic_kind": 0.5}

    def __init__(self, root: str | Path | None = None) -> None:
        base = root or os.getenv("ASSAY_MEMORY_ROOT") or Path.cwd() / ".assay" / "memory"
        self.root = Path(base)
        self._cache: dict[str, list[MemoryRecord]] = {}

    # -- storage -----------------------------------------------------------

    def _path(self, namespace: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", namespace or "default")
        return self.root / f"{safe}.jsonl"

    def _load(self, namespace: str) -> list[MemoryRecord]:
        if namespace in self._cache:
            return self._cache[namespace]
        path = self._path(namespace)
        records: list[MemoryRecord] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(MemoryRecord.from_dict(json.loads(line)))
                except Exception:
                    continue  # one corrupt line must not lose the rest
        self._cache[namespace] = records
        return records

    # -- Memory contract ---------------------------------------------------

    def write(self, record: MemoryRecord) -> MemoryRecord:
        record.id = record.id or uuid.uuid4().hex[:12]
        record.created_at = record.created_at or _now()
        if not record.entities:
            record.entities = extract_entities(record.content)

        path = self._path(record.namespace)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        self._cache.setdefault(record.namespace, []).append(record)
        return record

    def recall(
        self,
        query: str,
        *,
        namespace: str = "default",
        kind: str | None = None,
        limit: int = 5,
        entities: list[str] | None = None,
    ) -> list[MemoryRecord]:
        records = [r for r in self._load(namespace) if kind is None or r.kind == kind]
        if not records:
            return []

        query_tokens = tokenize(query)
        query_entities = {e.lower() for e in (entities or extract_entities(query))}

        scored: list[MemoryRecord] = []
        for record in records:
            score = self._score(record, query_tokens, query_entities)
            if score <= 0:
                continue
            # Copy so a recall score never mutates the stored record.
            hit = MemoryRecord.from_dict(record.to_dict())
            hit.score = round(score, 4)
            scored.append(hit)

        scored.sort(key=lambda r: (-r.score, r.created_at))
        return scored[:limit]

    def _score(self, record: MemoryRecord, query_tokens: set[str],
               query_entities: set[str]) -> float:
        record_entities = {e.lower() for e in record.entities}
        entity_hits = len(query_entities & record_entities)

        record_tokens = tokenize(record.content) | {t.lower() for t in record.tags}
        overlap = len(query_tokens & record_tokens)
        keyword = overlap / math.sqrt(len(record_tokens) or 1)

        # Exponential decay: a 30-day-old record is worth half a fresh one.
        recency = 0.5 ** (_age_days(record.created_at) / _HALF_LIFE_DAYS)

        # A recorded failure is worth more per token than a recorded success.
        outcome = 1.0 if record.outcome in ("failed", "verification_failed") else 0.0
        semantic = 1.0 if record.kind == "semantic" else 0.0

        score = (
            self.WEIGHTS["entity"] * entity_hits
            + self.WEIGHTS["keyword"] * keyword
            + self.WEIGHTS["recency"] * recency
            + self.WEIGHTS["outcome"] * outcome
            + self.WEIGHTS["semantic_kind"] * semantic
        )
        # Recency and kind alone must not surface an unrelated record.
        return score if (entity_hits or overlap or record.kind == "semantic") else 0.0

    def forget(self, *, namespace: str = "default", record_id: str | None = None) -> int:
        records = self._load(namespace)
        if record_id is None:
            removed = len(records)
            self._path(namespace).unlink(missing_ok=True)
            self._cache[namespace] = []
            return removed

        kept = [r for r in records if r.id != record_id]
        removed = len(records) - len(kept)
        if removed:
            path = self._path(namespace)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(json.dumps(r.to_dict(), ensure_ascii=False) + "\n" for r in kept),
                encoding="utf-8",
            )
            self._cache[namespace] = kept
        return removed

    def stats(self, *, namespace: str | None = None) -> dict:
        namespaces = [namespace] if namespace else self._namespaces()
        out: dict = {"namespaces": {}, "total": 0}
        for name in namespaces:
            records = self._load(name)
            kinds: dict[str, int] = {}
            for record in records:
                kinds[record.kind] = kinds.get(record.kind, 0) + 1
            out["namespaces"][name] = {
                "records": len(records),
                "kinds": kinds,
                "oldest": min((r.created_at for r in records), default=""),
                "newest": max((r.created_at for r in records), default=""),
                "path": str(self._path(name)),
            }
            out["total"] += len(records)
        return out

    def _namespaces(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.stem for p in self.root.glob("*.jsonl"))

    def all(self, namespace: str = "default") -> list[MemoryRecord]:
        return list(self._load(namespace))


class NullMemory:
    """Remembers nothing. The default when no ``memory:`` block is configured.

    Explicit rather than implicit: a harness with memory disabled reports so in its
    trajectory, instead of silently having none.
    """

    id = "null"
    contract_version = CONTRACT_VERSION

    def write(self, record: MemoryRecord) -> MemoryRecord:
        return record

    def recall(self, query, *, namespace="default", kind=None, limit=5, entities=None):
        return []

    def forget(self, *, namespace: str = "default", record_id: str | None = None) -> int:
        return 0

    def stats(self, *, namespace: str | None = None) -> dict:
        return {"namespaces": {}, "total": 0, "backend": "null"}


class InMemoryMemory(JsonlMemory):
    """Non-persistent variant for tests and ephemeral runs."""

    id = "memory"

    def __init__(self) -> None:  # noqa: D107
        super().__init__(root=Path("/nonexistent"))
        self._store: dict[str, list[MemoryRecord]] = {}
        self._cache = self._store

    def write(self, record: MemoryRecord) -> MemoryRecord:
        record.id = record.id or uuid.uuid4().hex[:12]
        record.created_at = record.created_at or _now()
        if not record.entities:
            record.entities = extract_entities(record.content)
        self._store.setdefault(record.namespace, []).append(record)
        return record

    def _load(self, namespace: str) -> list[MemoryRecord]:
        return self._store.setdefault(namespace, [])

    def forget(self, *, namespace: str = "default", record_id: str | None = None) -> int:
        records = self._store.get(namespace, [])
        if record_id is None:
            self._store[namespace] = []
            return len(records)
        kept = [r for r in records if r.id != record_id]
        self._store[namespace] = kept
        return len(records) - len(kept)

    def _namespaces(self) -> list[str]:
        return sorted(self._store)


def summarize_trajectory(trajectory, *, max_chars: int = 1200) -> str:
    """Condense a finished run into something worth remembering.

    Records what was *done and learned*, not the transcript. A memory that reproduces the
    conversation is a transcript with worse recall.
    """
    lines = [f"Goal: {trajectory.goal or '(none stated)'}",
             f"Outcome: {trajectory.status} — {trajectory.stop_reason}"]
    if trajectory.tool_call_names:
        lines.append("Tools used: " + " → ".join(trajectory.tool_call_names[:15]))

    errors = trajectory.tool_errors
    if errors:
        lines.append("Failures:")
        for error in errors[:4]:
            lines.append(f"  - {error.call.name}: {error.content.strip()[:120]}")

    denied = trajectory.denied_calls
    if denied:
        lines.append("Blocked by policy: "
                     + ", ".join(f"{d.call.name} ({d.denied_reason[:60]})" for d in denied[:3]))

    if trajectory.output:
        lines.append("Result: " + trajectory.output.strip().replace("\n", " ")[:300])

    lines.append(f"Cost: ${trajectory.cost_usd:.4f} over {trajectory.iterations} iteration(s)")
    return "\n".join(lines)[:max_chars]

"""Progressive disclosure — three-tier loading for a prompt library.

The problem
-----------
A prompt library's whole value is having many prompts. But an MCP server that returns
full metadata for every prompt spends the client's context before any work begins. At
twenty prompts nobody notices. At the two hundred the roadmap promises, the library is a
context tax rather than an asset.

The pattern
-----------
Anthropic's Skills mechanism established the measured answer: **load in tiers, on demand.**
Names and one-line descriptions first, full body only when the model selects one, bundled
files only when read. The reported effect is 50 skills compressed from ~150,000 tokens to
~2,000 — a median discovery cost near 80 tokens per skill.

A prompt library is exactly the artifact this was designed for. See
``docs/architecture/RESEARCH.md`` §3.4.

Tiers here
----------
=====  ==========================================  ==============================
Tier   Content                                     Loaded when
=====  ==========================================  ==============================
1      ``id``, title, one-line summary             always, at ``prompts/list``
2      full messages, schemas, model binding       ``prompts/get`` / ``assay_get``
3      attachments and referenced datasets         explicitly read
=====  ==========================================  ==============================

Two details that matter as much as the tiering:

* **Ordering is stable and content-derived.** Tier-1 output must not reshuffle between
  calls, because a changed prefix invalidates the client's prompt cache and silently
  multiplies cost.
* **The budget is enforced, not advisory.** When the index exceeds its allowance, entries
  are dropped deterministically (lowest priority first) and the omission is *reported*
  rather than hidden — a silently truncated index is worse than a small one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

#: Characters per token. Deliberately a rough estimate: an exact count needs a
#: provider-specific tokenizer, which would couple this module to a provider. Slightly
#: over-estimating is the safe direction for a budget.
CHARS_PER_TOKEN = 4

#: Ceiling on a single tier-1 description, matching the convention that made the
#: measured savings possible. Enforced by the linter, truncated here as a backstop.
MAX_SUMMARY_CHARS = 250

#: Default tier-1 allowance: ~1% of a 200k context window.
DEFAULT_INDEX_TOKEN_BUDGET = 2000


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_payload_tokens(payload: Any) -> int:
    """Token estimate for a structure about to be serialised into context."""
    import json

    try:
        return estimate_tokens(json.dumps(payload, default=str, ensure_ascii=False))
    except Exception:
        return estimate_tokens(str(payload))


@dataclass(slots=True)
class DisclosureBudget:
    """Limits for the tier-1 index."""

    max_tokens: int = DEFAULT_INDEX_TOKEN_BUDGET
    max_summary_chars: int = MAX_SUMMARY_CHARS
    #: Statuses excluded from the index entirely. Archived prompts still resolve by id.
    exclude_status: frozenset[str] = frozenset({"archived"})
    #: When true, deprecated prompts are listed but marked.
    include_deprecated: bool = True

    @classmethod
    def from_config(cls, config: dict | None) -> "DisclosureBudget":
        config = config or {}
        return cls(
            max_tokens=int(config.get("max_tokens", DEFAULT_INDEX_TOKEN_BUDGET)),
            max_summary_chars=int(config.get("max_summary_chars", MAX_SUMMARY_CHARS)),
            exclude_status=frozenset(config.get("exclude_status", ["archived"])),
            include_deprecated=bool(config.get("include_deprecated", True)),
        )


@dataclass(slots=True)
class IndexEntry:
    """One tier-1 record — the whole of what a client sees before selecting."""

    id: str
    title: str
    summary: str
    kind: str = "prompt"
    status: str = "draft"
    tags: list[str] = field(default_factory=list)
    version: int = 1
    tokens: int = 0

    def to_dict(self) -> dict:
        """Tier-1 payload — deliberately minimal.

        ``version`` and ``kind`` are omitted at tier 1: neither helps a client *decide*
        whether to load a prompt, and at library scale every field is multiplied by the
        entry count. They are present at tier 2. Measured effect: dropping them takes an
        entry from ~99 to ~80 tokens, matching the per-skill figure the pattern reports.
        """
        payload = {"id": self.id, "title": self.title, "summary": self.summary}
        if self.status != "stable":
            payload["status"] = self.status
        if self.tags:
            payload["tags"] = self.tags[:4]
        return payload

    def to_dict_full(self) -> dict:
        return {
            "id": self.id, "title": self.title, "summary": self.summary,
            "kind": self.kind, "status": self.status,
            "tags": self.tags, "version": self.version,
        }


@dataclass(slots=True)
class IndexReport:
    """What building the index cost, and what it left out.

    Exists so the saving is *measured* rather than claimed, and so omissions are visible.
    """

    entries: list[IndexEntry] = field(default_factory=list)
    included: int = 0
    omitted: list[str] = field(default_factory=list)
    excluded_by_status: list[str] = field(default_factory=list)
    truncated_summaries: list[str] = field(default_factory=list)
    index_tokens: int = 0
    full_tokens: int = 0
    budget_tokens: int = 0
    #: Tier-0: namespace → count. What exists, without enumerating it.
    namespaces: dict[str, int] = field(default_factory=dict)

    @property
    def saved_tokens(self) -> int:
        return max(0, self.full_tokens - self.index_tokens)

    @property
    def saving_ratio(self) -> float:
        if not self.full_tokens:
            return 0.0
        return round(1 - (self.index_tokens / self.full_tokens), 4)

    @property
    def tokens_per_entry(self) -> float:
        return round(self.index_tokens / self.included, 1) if self.included else 0.0

    def to_dict(self) -> dict:
        return {
            "included": self.included,
            "namespaces": self.namespaces,
            "omitted": self.omitted,
            "excluded_by_status": self.excluded_by_status,
            "truncated_summaries": self.truncated_summaries,
            "index_tokens": self.index_tokens,
            "full_tokens": self.full_tokens,
            "budget_tokens": self.budget_tokens,
            "saved_tokens": self.saved_tokens,
            "saving_ratio": self.saving_ratio,
            "tokens_per_entry": self.tokens_per_entry,
        }


_WHITESPACE = re.compile(r"\s+")


def summarize(prompt: Any, *, max_chars: int = MAX_SUMMARY_CHARS) -> tuple[str, bool]:
    """Derive a one-line tier-1 summary. Returns ``(summary, was_truncated)``.

    Preference order: an explicit ``summary`` field, then ``description``, then the first
    sentence of the body. Falling back to the body is a courtesy for undocumented prompts,
    not an endorsement — the linter still asks for a description.
    """
    raw = (
        prompt.data.get("summary")
        or prompt.data.get("description")
        or _first_sentence(prompt.body)
        or prompt.name
        or prompt.id
    )
    flat = _WHITESPACE.sub(" ", str(raw)).strip()
    if len(flat) <= max_chars:
        return flat, False
    return flat[: max_chars - 1].rstrip() + "…", True


def _first_sentence(body: str) -> str:
    text = _WHITESPACE.sub(" ", (body or "").strip())
    if not text:
        return ""
    match = re.search(r"^(.{20,200}?[.!?])(\s|$)", text)
    return match.group(1) if match else text[:200]


def _priority(prompt: Any) -> tuple:
    """Deterministic ordering, most useful first.

    Stability matters more than cleverness here: a reordered prefix invalidates the
    client's prompt cache. Ties break on id, which never changes.
    """
    status_rank = {"stable": 0, "review": 1, "draft": 2, "deprecated": 3, "archived": 4}
    return (
        status_rank.get(prompt.status, 5),
        0 if prompt.evals else 1,     # tested prompts before untested ones
        prompt.id,
    )


def build_index(
    prompts: Iterable[Any],
    *,
    budget: DisclosureBudget | None = None,
) -> IndexReport:
    """Build the tier-1 index under a token budget.

    ``prompts`` are ``PromptFile`` objects. The report records both what was included and
    what the full payload *would* have cost, so the saving is measurable.
    """
    budget = budget or DisclosureBudget()
    report = IndexReport(budget_tokens=budget.max_tokens)

    candidates = []
    for prompt in prompts:
        if prompt.status in budget.exclude_status:
            report.excluded_by_status.append(prompt.id)
            continue
        if prompt.status == "deprecated" and not budget.include_deprecated:
            report.excluded_by_status.append(prompt.id)
            continue
        candidates.append(prompt)
        # Tier-2 cost is what a naive server would have spent on this prompt.
        report.full_tokens += estimate_payload_tokens(prompt.to_dict())

    candidates.sort(key=_priority)

    # Tier 0: the namespace map. At library scale the budget cannot list everything, and
    # "180 omitted, use search" tells a client nothing about *what* it is missing. A
    # namespace histogram costs a few dozen tokens and conveys the shape of the library,
    # so search queries are informed rather than blind.
    for prompt in candidates:
        namespace = prompt.id.split("/", 1)[0] if "/" in prompt.id else "(root)"
        report.namespaces[namespace] = report.namespaces.get(namespace, 0) + 1

    spent = estimate_payload_tokens(report.namespaces)
    for prompt in candidates:
        summary, truncated = summarize(prompt, max_chars=budget.max_summary_chars)
        if truncated:
            report.truncated_summaries.append(prompt.id)
        entry = IndexEntry(
            id=prompt.id,
            title=prompt.name,
            summary=summary,
            kind=prompt.kind,
            status=prompt.status,
            tags=prompt.tags,
            version=prompt.version,
        )
        entry.tokens = estimate_payload_tokens(entry.to_dict())
        if spent + entry.tokens > budget.max_tokens and report.entries:
            # Budget reached. Everything after this is omitted, and named as such.
            report.omitted = [p.id for p in candidates[candidates.index(prompt):]]
            break
        spent += entry.tokens
        report.entries.append(entry)

    report.included = len(report.entries)
    report.index_tokens = spent
    return report


def tier_two(prompt: Any) -> dict:
    """Tier-2 payload: everything needed to *use* the prompt, minus attachments.

    Attachments and datasets stay at tier 3 — referenced by handle so the model can pull
    them if it needs them. That is the just-in-time retrieval pattern: identifiers in
    context, content on demand.
    """
    payload = prompt.to_dict()
    attachments = payload.pop("attachments", None)
    if attachments:
        payload["attachment_refs"] = [
            a.get("ref") for a in attachments if isinstance(a, dict) and a.get("ref")
        ]
    return payload


def workspace_report(prompts: Iterable[Any], *, budget: DisclosureBudget | None = None) -> dict:
    """Full accounting for ``assay tokens`` — what the library costs a client, tier by tier."""
    prompts = list(prompts)
    report = build_index(prompts, budget=budget)
    per_prompt = sorted(
        (
            {
                "id": p.id,
                "tier1_tokens": estimate_payload_tokens(
                    IndexEntry(
                        id=p.id, title=p.name,
                        summary=summarize(p, max_chars=(budget or DisclosureBudget()).max_summary_chars)[0],
                        kind=p.kind, status=p.status, tags=p.tags, version=p.version,
                    ).to_dict()
                ),
                "tier2_tokens": estimate_payload_tokens(tier_two(p)),
            }
            for p in prompts
        ),
        key=lambda row: -row["tier2_tokens"],
    )
    return {
        "prompts": len(prompts),
        "index": report.to_dict(),
        "heaviest": per_prompt[:10],
        "naive_total_tokens": report.full_tokens,
        "disclosed_total_tokens": report.index_tokens,
    }

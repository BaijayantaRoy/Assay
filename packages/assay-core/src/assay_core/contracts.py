"""Stable plugin contracts.

Everything pluggable in Assay implements one of the Protocols below.
Core never imports a concrete implementation; it resolves one from the registry.

Compatibility rules
-------------------
Each contract declares ``CONTRACT_VERSION``. A plugin declares which contract
version it implements via the class attribute ``contract_version``. The registry
refuses to load a plugin whose contract major version differs from core's.

Adding an *optional* method or an optional keyword argument bumps the minor
version and is backward compatible. Removing or changing the meaning of anything
bumps the major version, and the previous major stays supported for at least
twelve months alongside it (see docs/architecture/adr/0004-compatibility-policy.md).

This is the mechanism that makes "anything new in five years drops in without
touching core" a structural property rather than an aspiration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterable, Protocol, runtime_checkable

CONTRACT_VERSION = "1.1"

# ---------------------------------------------------------------------------
# Shared value objects
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Message:
    """One chat message, provider-neutral."""

    role: str
    content: Any  # str | list[ContentPart-like dicts]
    name: str | None = None
    cache: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.cache:
            d["cache"] = True
        d.update(self.extra)
        return d


@dataclass(slots=True)
class RenderedPrompt:
    """Output of the render stage: what will actually be sent."""

    messages: list[Message]
    model: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    provider_params: dict[str, Any] = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)
    output_schema: dict | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    renderer: str = "jinja2"

    @property
    def text(self) -> str:
        """Flattened plain-text view, for logging and non-chat providers."""
        parts = []
        for m in self.messages:
            body = m.content if isinstance(m.content, str) else str(m.content)
            parts.append(f"[{m.role}] {body}")
        return "\n\n".join(parts)


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class Completion:
    """Provider-neutral result of one model call."""

    text: str
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    cost_usd: float = 0.0
    finish_reason: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "cached_input_tokens": self.usage.cached_input_tokens,
                "reasoning_tokens": self.usage.reasoning_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "finish_reason": self.finish_reason,
            "tool_calls": self.tool_calls,
            "trace_id": self.trace_id,
        }


@dataclass(slots=True)
class StreamChunk:
    """One provider-neutral incremental completion fragment.

    ``text`` is a delta, never the accumulated answer. Providers attach usage and a
    finish reason when those fields become available, normally on the final chunk.
    ``tool_calls`` may contain complete calls or fragments keyed by a stable ``index``;
    fragmented ``arguments`` are JSON strings and complete arguments are dictionaries.
    """

    text: str = ""
    model: str = ""
    provider: str = ""
    usage: Usage | None = None
    cost_usd: float | None = None
    finish_reason: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "usage": None if self.usage is None else {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "cached_input_tokens": self.usage.cached_input_tokens,
                "reasoning_tokens": self.usage.reasoning_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "cost_usd": self.cost_usd,
            "finish_reason": self.finish_reason,
            "tool_calls": self.tool_calls,
        }


@dataclass(slots=True)
class ModelInfo:
    """What a provider knows about one model."""

    id: str
    provider: str
    display_name: str = ""
    context_window: int = 0
    max_output_tokens: int = 0
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0
    cached_input_cost_per_mtok: float = 0.0
    capabilities: frozenset[str] = frozenset()
    deprecated: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalResult:
    passed: bool
    score: float
    evaluator: str
    reason: str = ""
    weight: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Harness and loop value objects
#
# A prompt produces one Completion. A *harness* produces a Trajectory: the whole
# sequence of model turns, tool calls, observations and control decisions. Making
# that sequence a first-class, serialisable object is what allows it to be
# asserted on, diffed, and version-controlled like any other artifact.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ToolCall:
    """One tool invocation requested by the model."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "arguments": self.arguments, "id": self.id}


@dataclass(slots=True)
class ToolResult:
    """The observation returned to the model after a tool ran."""

    call: ToolCall
    content: str = ""
    is_error: bool = False
    latency_ms: int = 0
    #: Set when a controller blocked the call rather than executing it.
    denied: bool = False
    denied_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "tool": self.call.name,
            "arguments": self.call.arguments,
            "content": self.content[:4000],
            "is_error": self.is_error,
            "denied": self.denied,
            "denied_reason": self.denied_reason,
            "latency_ms": self.latency_ms,
        }


@dataclass(slots=True)
class Step:
    """One iteration of an agent loop: think → act → observe."""

    index: int
    completion: Completion | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    text: str = ""
    context_tokens: int = 0
    #: Set when a context strategy reshaped the window before this step.
    context_action: str = ""
    #: Provider delivery evidence when this model turn consumed a stream.
    streaming: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        payload = {
            "index": self.index,
            "text": self.text,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "tool_results": [r.to_dict() for r in self.tool_results],
            "context_tokens": self.context_tokens,
            "context_action": self.context_action,
            "cost_usd": self.completion.cost_usd if self.completion else 0.0,
            "latency_ms": self.completion.latency_ms if self.completion else 0,
        }
        if self.streaming is not None:
            payload["streaming"] = self.streaming
        return payload


@dataclass(slots=True)
class Budget:
    """Hard ceilings on one harness run. Exceeding any of them halts the loop.

    A loop without a budget is an unbounded spend, and an unbounded spend is an
    incident waiting for a trigger.
    """

    cost_usd: float | None = None
    tokens: int | None = None
    wallclock_s: float | None = None
    iterations: int | None = None
    tool_calls: int | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "Budget":
        data = data or {}
        return cls(
            cost_usd=data.get("cost_usd"),
            tokens=data.get("tokens"),
            wallclock_s=data.get("wallclock_s"),
            iterations=data.get("iterations"),
            tool_calls=data.get("tool_calls"),
        )

    def to_dict(self) -> dict:
        return {k: v for k, v in {
            "cost_usd": self.cost_usd, "tokens": self.tokens,
            "wallclock_s": self.wallclock_s, "iterations": self.iterations,
            "tool_calls": self.tool_calls,
        }.items() if v is not None}


@dataclass(slots=True)
class Trajectory:
    """The complete record of a harness run.

    This is the unit that harness evals assert against. The final answer is only one
    field of it — most interesting agent failures are visible in the *shape* of the
    trajectory (looping on one tool, answering without searching, blowing the budget)
    and invisible in the output alone.
    """

    harness_id: str = ""
    harness_version: int = 1
    goal: str = ""
    steps: list[Step] = field(default_factory=list)
    output: str = ""
    #: "completed" | "budget_exceeded" | "max_iterations" | "stopped" | "failed" | "denied"
    status: str = "completed"
    stop_reason: str = ""
    cost_usd: float = 0.0
    total_tokens: int = 0
    wallclock_s: float = 0.0
    model: str = ""
    budget: Budget = field(default_factory=Budget)
    #: Populated by a loop's verification step, when there is one.
    verified: bool | None = None
    verification_detail: str = ""
    events: list[dict] = field(default_factory=list)
    run_id: str = ""

    # -- derived views used heavily by trajectory evaluators ---------------

    @property
    def iterations(self) -> int:
        return len(self.steps)

    @property
    def tool_call_names(self) -> list[str]:
        """Flat, ordered list of every tool invoked."""
        return [c.name for step in self.steps for c in step.tool_calls]

    @property
    def all_tool_results(self) -> list[ToolResult]:
        return [r for step in self.steps for r in step.tool_results]

    @property
    def tool_errors(self) -> list[ToolResult]:
        """Calls that were permitted and then failed.

        Denied calls are excluded deliberately, even though they also carry
        ``is_error`` so the model sees the call did not succeed. A blocked call is a
        control working, not a malfunction — counting it here would make a harness whose
        deny list fired look broken, fail a ``no_tool_errors`` assertion for doing its
        job, and show a warning in the workbench for a successful defence.

        Use :attr:`denied_calls` for the security-relevant view.
        """
        return [r for r in self.all_tool_results if r.is_error and not r.denied]

    @property
    def denied_calls(self) -> list[ToolResult]:
        return [r for r in self.all_tool_results if r.denied]

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "harness_id": self.harness_id,
            "harness_version": self.harness_version,
            "goal": self.goal,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "output": self.output,
            "iterations": self.iterations,
            "tool_calls": self.tool_call_names,
            "tool_errors": len(self.tool_errors),
            "denied_calls": [r.to_dict() for r in self.denied_calls],
            "cost_usd": round(self.cost_usd, 8),
            "total_tokens": self.total_tokens,
            "wallclock_s": round(self.wallclock_s, 3),
            "model": self.model,
            "budget": self.budget.to_dict(),
            "verified": self.verified,
            "verification_detail": self.verification_detail,
            "steps": [s.to_dict() for s in self.steps],
            "events": self.events,
        }


@dataclass(slots=True)
class CycleResult:
    """One pass of an outer loop: run the steps, then verify."""

    index: int
    step_results: list[dict] = field(default_factory=list)
    verified: bool | None = None
    verification_detail: str = ""
    cost_usd: float = 0.0
    wallclock_s: float = 0.0
    goal_met: bool = False
    orchestration: str = "sequential"
    route: list[str] = field(default_factory=list)
    handoff_cycle: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cycle": self.index,
            "steps": self.step_results,
            "verified": self.verified,
            "verification_detail": self.verification_detail,
            "goal_met": self.goal_met,
            "cost_usd": round(self.cost_usd, 8),
            "wallclock_s": round(self.wallclock_s, 3),
            "orchestration": self.orchestration,
            "route": self.route,
            "handoff_cycle": self.handoff_cycle,
        }


@dataclass(slots=True)
class LoopRun:
    """The complete record of an outer-loop run."""

    loop_id: str = ""
    loop_version: int = 1
    goal: str = ""
    trigger: str = "manual"
    cycles: list[CycleResult] = field(default_factory=list)
    #: "goal_met" | "max_cycles" | "budget_exceeded" | "verification_failed" |
    #: "stalled" | "routing_loop" | "failed"
    status: str = "goal_met"
    stop_reason: str = ""
    cost_usd: float = 0.0
    wallclock_s: float = 0.0
    state: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""

    @property
    def cycle_count(self) -> int:
        return len(self.cycles)

    @property
    def goal_met(self) -> bool:
        return self.status == "goal_met"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "loop_id": self.loop_id,
            "loop_version": self.loop_version,
            "goal": self.goal,
            "trigger": self.trigger,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "goal_met": self.goal_met,
            "cycles": [c.to_dict() for c in self.cycles],
            "cycle_count": self.cycle_count,
            "cost_usd": round(self.cost_usd, 8),
            "wallclock_s": round(self.wallclock_s, 3),
            "state": self.state,
        }


@dataclass(slots=True)
class GuardrailResult:
    allowed: bool
    action: str = "block"  # block | warn | redact | retry
    reason: str = ""
    transformed: str | None = None  # set when action == redact
    guardrail: str = ""


# ---------------------------------------------------------------------------
# Plugin base
# ---------------------------------------------------------------------------


@runtime_checkable
class Plugin(Protocol):
    """Every plugin exposes identity and the contract version it targets."""

    id: str
    contract_version: str


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


@runtime_checkable
class Renderer(Protocol):
    """Turns a template + variables into a string.

    Entry point group: ``assay.renderers``. Selected by ``engine.template``.
    """

    id: str
    contract_version: str

    def render(self, template: str, variables: dict[str, Any], *, strict: bool = True) -> str: ...

    def variables_of(self, template: str) -> set[str]:
        """Best-effort static extraction of referenced variable names."""
        ...


@runtime_checkable
class Provider(Protocol):
    """Talks to one model API family.

    Entry point group: ``assay.providers``. Selected by the ``provider/`` prefix of a
    model reference, or by explicit workspace configuration.

    A provider is responsible for mapping portable ``params`` onto its native API and
    for passing ``provider_params[self.id]`` through untouched.
    """

    id: str
    contract_version: str

    def capabilities(self, model: str) -> frozenset[str]:
        """Capability strings this provider+model can satisfy (open vocabulary)."""
        ...

    def list_models(self) -> Iterable[ModelInfo]:
        """Models known to this provider. May hit the network; callers should cache."""
        ...

    def complete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion: ...

    # Async and streaming are separate optional protocols. Core feature-detects them;
    # providers that only implement this stable synchronous contract remain valid.


@runtime_checkable
class AsyncProvider(Protocol):
    """Optional provider extension for non-blocking completion calls.

    Entry-point plugins targeting contract 1.0 remain compatible. Runtime falls back to
    executing their synchronous ``complete`` method in a worker thread.
    """

    id: str
    contract_version: str

    async def acomplete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion: ...


@runtime_checkable
class StreamingProvider(Protocol):
    """Optional async delta extension for text and tool-call completions.

    Runtime feature-detects this protocol. A provider without it still works through a
    single buffered delta, which is explicitly labelled in run evidence.
    """

    id: str
    contract_version: str

    def astream(
        self, prompt: RenderedPrompt, **kwargs: Any
    ) -> AsyncIterator[StreamChunk]: ...


@runtime_checkable
class Evaluator(Protocol):
    """Scores one output against one assertion.

    Entry point group: ``assay.evaluators``. Selected by assertion ``type``.
    """

    id: str
    contract_version: str

    def evaluate(
        self,
        output: str,
        *,
        assertion: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> EvalResult: ...


@runtime_checkable
class Guardrail(Protocol):
    """Validates or transforms input, output, or a tool result.

    Entry point group: ``assay.guardrails``. Selected by guardrail ``type``.
    """

    id: str
    contract_version: str
    stages: frozenset[str]  # subset of {"input", "output", "tool_result"}

    def check(
        self,
        text: str,
        *,
        config: dict[str, Any],
        stage: str,
        context: dict[str, Any] | None = None,
    ) -> GuardrailResult: ...


@runtime_checkable
class Store(Protocol):
    """Persistence backend for PromptFiles.

    Entry point group: ``assay.stores``. The file store is canonical; database,
    object-storage, and remote-registry stores implement the same five methods.
    """

    id: str
    contract_version: str

    def list(self, *, prefix: str | None = None) -> Iterable[str]: ...
    def get(self, prompt_id: str, *, version: int | None = None) -> Any: ...
    def put(self, prompt: Any, *, message: str | None = None) -> Any: ...
    def delete(self, prompt_id: str) -> None: ...
    def history(self, prompt_id: str) -> Iterable[dict]: ...


@runtime_checkable
class ToolProvider(Protocol):
    """Supplies executable tools to a harness.

    Entry point group: ``assay.tools``. A provider may expose many tools; harness files
    reference them as ``namespace.tool`` (for example ``fs.read``).

    This is the *tool interface* element of an agent harness. Keeping it a plugin means
    a company can expose its internal systems to every harness in the workspace by
    installing one package, and every harness gets the same audit and control path.
    """

    id: str
    contract_version: str

    def list_tools(self) -> Iterable[dict]:
        """Tool declarations: ``{name, description, input_schema}``."""
        ...

    def call(self, name: str, arguments: dict[str, Any], *, context: dict[str, Any]) -> ToolResult:
        """Execute one tool. Must not raise for ordinary failure — return ``is_error``.

        An exception aborts the whole harness run; a tool that returns an error lets the
        model see what went wrong and recover, which is usually what you want.
        """
        ...


@runtime_checkable
class ContextStrategy(Protocol):
    """Decides what stays in the context window between iterations.

    Entry point group: ``assay.context``. Selected by ``harness.context.strategy``.

    This is the *context management* element of a harness, and it is the element that
    most often determines whether a long-running agent succeeds or degrades: an agent
    that loses the goal at step 30 usually lost it to a naive truncation.
    """

    id: str
    contract_version: str

    def apply(
        self,
        messages: list[Message],
        *,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[list[Message], str]:
        """Return the reshaped messages and a short description of what was done."""
        ...


@runtime_checkable
class Controller(Protocol):
    """Enforces control mechanisms over a harness run.

    Entry point group: ``assay.controllers``. This is the *control* element of a harness:
    permission gates, deny lists, sandbox roots, approval requirements.

    Consulted before every tool call and at every iteration boundary, so a policy can
    halt a run rather than only auditing it afterwards.
    """

    id: str
    contract_version: str

    def before_tool(
        self,
        call: ToolCall,
        *,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> GuardrailResult:
        """Allow, deny, or transform a tool call before it executes."""
        ...

    def before_iteration(
        self,
        trajectory: Trajectory,
        *,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> GuardrailResult:
        """Allow or halt the next iteration. Called with the trajectory so far."""
        ...


@dataclass(slots=True)
class MemoryRecord:
    """One thing an agent remembers.

    Two kinds, following the split the literature settles on:

    ``episodic``
        A concrete past event — a trajectory, an outcome, a specific failure. Answers
        "what happened last time I tried this?"
    ``semantic``
        A distilled rule, preference or convention. Answers "what do I know about how
        things work here?" Fewer, more valuable, and expensive to derive.

    A record is data, not cognition. The sceptical reading in the literature is worth
    keeping: much of what is marketed as agent memory is retrieval with extra steps. This
    design agrees, and treats memory as a retrieval-and-persistence problem.
    """

    content: str
    kind: str = "episodic"                      # episodic | semantic
    id: str = ""
    namespace: str = "default"
    tags: list[str] = field(default_factory=list)
    #: Extracted identifiers — file paths, ids, names — used for entity-match recall.
    entities: list[str] = field(default_factory=list)
    #: Where it came from, so a recalled claim can be traced to its origin.
    source_run_id: str = ""
    source_id: str = ""                          # harness or prompt id
    outcome: str = ""                            # completed | failed | verified | ...
    created_at: str = ""
    #: Populated by recall, not by the writer.
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "namespace": self.namespace,
            "content": self.content, "tags": self.tags, "entities": self.entities,
            "source_run_id": self.source_run_id, "source_id": self.source_id,
            "outcome": self.outcome, "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        known = {f for f in (
            "content", "kind", "id", "namespace", "tags", "entities",
            "source_run_id", "source_id", "outcome", "created_at",
        )}
        return cls(**{k: v for k, v in data.items() if k in known})


@runtime_checkable
class Memory(Protocol):
    """Persistent memory across agent runs.

    Entry point group: ``assay.memory``. Selected by ``harness.memory.backend``.

    Memory is a **separate architectural component**, not a longer prompt: it survives
    the context window, is written deliberately rather than accumulated, and is recalled
    by relevance rather than recency alone.

    Implementations should treat ``recall`` as hybrid — keyword, entity and recency at
    minimum, embeddings where available — because pure vector similarity misses exact
    identifiers, which are precisely what agents need to avoid repeating work.
    """

    id: str
    contract_version: str

    def write(self, record: MemoryRecord) -> MemoryRecord: ...

    def recall(
        self,
        query: str,
        *,
        namespace: str = "default",
        kind: str | None = None,
        limit: int = 5,
        entities: list[str] | None = None,
    ) -> list[MemoryRecord]: ...

    def forget(self, *, namespace: str = "default", record_id: str | None = None) -> int: ...

    def stats(self, *, namespace: str | None = None) -> dict: ...


@runtime_checkable
class Importer(Protocol):
    """Reads a foreign format into PromptFiles. Entry point group: ``assay.importers``."""

    id: str
    contract_version: str

    def detect(self, data: Any) -> bool: ...
    def to_promptfiles(self, data: Any) -> list[Any]: ...


@runtime_checkable
class Exporter(Protocol):
    """Writes PromptFiles to a foreign format. Entry point group: ``assay.exporters``."""

    id: str
    contract_version: str

    def from_promptfiles(self, prompts: list[Any]) -> Any: ...


@runtime_checkable
class Tracer(Protocol):
    """Observability sink. Entry point group: ``assay.tracers``.

    The built-in OpenTelemetry tracer emits ``gen_ai.*`` semantic-convention spans.
    Content capture is opt-in and uses span events rather than indexable attributes.
    """

    id: str
    contract_version: str

    def on_run(self, *, prompt: RenderedPrompt, completion: Completion, meta: dict) -> None: ...


@runtime_checkable
class Optimizer(Protocol):
    """Rewrites a prompt to improve a score. Entry point group: ``assay.optimizers``.

    Covers everything from a single LLM rewrite pass to DSPy/GEPA-style search.
    """

    id: str
    contract_version: str

    def optimize(self, prompt: Any, *, dataset: list[dict], budget: dict | None = None) -> Any: ...


#: Entry-point group -> the Protocol implementations must satisfy.
CONTRACT_GROUPS: dict[str, type] = {
    "assay.renderers": Renderer,
    "assay.providers": Provider,
    "assay.evaluators": Evaluator,
    "assay.guardrails": Guardrail,
    "assay.stores": Store,
    "assay.importers": Importer,
    "assay.exporters": Exporter,
    "assay.tracers": Tracer,
    "assay.optimizers": Optimizer,
    # Harness extension points — the four elements of an agent harness map onto
    # these plus the existing provider contract (the agent loop itself).
    "assay.tools": ToolProvider,
    "assay.context": ContextStrategy,
    "assay.controllers": Controller,
    "assay.memory": Memory,
}

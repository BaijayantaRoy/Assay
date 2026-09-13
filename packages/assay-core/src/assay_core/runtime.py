"""The runtime: render → guard → execute → guard → trace.

This is the only place that composes plugins. It contains no vendor knowledge and no
format knowledge beyond the PromptFile document model, which is why a new provider,
renderer, evaluator or guardrail never requires a change here.

Execution order
---------------
1. Resolve renderer, provider, model, params.
2. Verify ``requires.capabilities`` — **fail closed**, never silently degrade.
3. Render every message.
4. Input guardrails.
5. Provider call, with ``model.fallbacks`` on hard failure.
6. Output guardrails (``retry`` re-runs once with a repair instruction).
7. Emit to every registered tracer.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, AsyncIterator, Callable

from . import environment as environment_mod
from .builtins.evaluators import aggregate
from .catalog import ModelCatalog, parse_model_ref
from .contracts import Completion, EvalResult, Message, RenderedPrompt, StreamChunk, Usage
from .errors import CapabilityError, GuardrailViolation, ProviderError, RateLimitError
from .evaluation import (
    accuracy_cost_report,
    failure_attribution,
    resolve_eval_cases,
    score_confidence_interval,
)
from .promptfile import PromptFile
from .registry import Registry, get_registry
from .workspace import Workspace

logger = logging.getLogger("assay.runtime")

MAX_GUARDRAIL_RETRIES = 1
MAX_STREAM_CHUNKS = 100_000
MAX_STREAM_CHUNK_BYTES = 1024 * 1024
MAX_STREAM_OUTPUT_BYTES = 16 * 1024 * 1024
RUNTIME_PARAM_KEYS = frozenset({
    "samples", "selection", "verifier",
    "rate_limit_retries", "rate_limit_backoff_s", "rate_limit_max_wait_s",
})
SELECTION_PARAM_KEYS = frozenset({"samples", "selection", "verifier"})
REPAIR_INSTRUCTION = (
    "Your previous response violated an output constraint: {reason}. "
    "Return a corrected response that satisfies the constraint. Output only the response."
)


def _candidate_key(completion: Completion) -> str:
    """Canonical vote key covering both text answers and proposed tool calls."""
    text = " ".join(completion.text.split()).casefold()
    tools = json.dumps(completion.tool_calls, sort_keys=True, default=str, ensure_ascii=False)
    return text + "\0" + tools


def _tool_fragment(raw: dict[str, Any], position: int) -> dict[str, Any]:
    """Convert a provider tool-call delta to Assay's small portable shape.

    OpenAI-shaped providers nest ``name`` and ``arguments`` below ``function``;
    Anthropic, Google, Ollama and third-party plugins commonly provide them directly.
    Keeping both shapes at the provider boundary lets old plugins stream complete tool
    calls without adopting a new vendor-specific representation.
    """
    if not isinstance(raw, dict):
        raise ProviderError("streamed tool-call fragments must be objects")
    function = raw.get("function") if isinstance(raw.get("function"), dict) else {}
    index = raw.get("index", position)
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ProviderError(
            "streamed tool-call index must be a non-negative integer",
            tool_call_index=index,
        )
    arguments = raw.get("arguments", function.get("arguments", ""))
    if arguments is None:
        arguments = ""
    if not isinstance(arguments, (str, dict)):
        raise ProviderError(
            "streamed tool-call arguments must be a JSON fragment or object",
            tool_call_index=index,
        )
    name = raw.get("name", function.get("name", "")) or ""
    call_id = raw.get("id")
    if not isinstance(name, str) or (call_id is not None and not isinstance(call_id, str)):
        raise ProviderError("streamed tool-call id and name must be strings")
    return {"index": index, "id": call_id, "name": name, "arguments": arguments}


def _merge_stream_tool_calls(chunks: list[StreamChunk]) -> list[dict[str, Any]]:
    """Assemble fragmented tool calls deterministically or fail closed.

    A malformed or incomplete argument stream is not silently converted to ``{}``:
    doing that would make the recorded trajectory differ from what the model emitted.
    """
    states: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for chunk in chunks:
        for position, raw in enumerate(chunk.tool_calls):
            fragment = _tool_fragment(raw, position)
            index = fragment["index"]
            if index not in states:
                states[index] = {"id": None, "name": "", "parts": [], "object": None}
                order.append(index)
            state = states[index]
            if fragment["id"]:
                if state["id"] not in (None, fragment["id"]):
                    raise ProviderError(
                        "streamed tool-call id changed mid-call", tool_call_index=index
                    )
                state["id"] = fragment["id"]
            if fragment["name"]:
                if state["name"] not in ("", fragment["name"]):
                    raise ProviderError(
                        "streamed tool-call name changed mid-call", tool_call_index=index
                    )
                state["name"] = fragment["name"]
            arguments = fragment["arguments"]
            if isinstance(arguments, dict):
                if state["parts"] or state["object"] is not None:
                    raise ProviderError(
                        "streamed tool-call arguments were emitted more than once",
                        tool_call_index=index,
                    )
                state["object"] = arguments
            elif arguments:
                if state["object"] is not None:
                    raise ProviderError(
                        "streamed tool-call mixed complete and fragmented arguments",
                        tool_call_index=index,
                    )
                state["parts"].append(arguments)

    merged: list[dict[str, Any]] = []
    for index in order:
        state = states[index]
        if not state["name"]:
            raise ProviderError(
                "streamed tool call completed without a name", tool_call_index=index
            )
        arguments = state["object"]
        if arguments is None:
            encoded = "".join(state["parts"]) or "{}"
            try:
                arguments = json.loads(encoded)
            except (TypeError, ValueError) as exc:
                raise ProviderError(
                    "streamed tool-call arguments are incomplete or invalid JSON",
                    tool_call_index=index,
                ) from exc
            if not isinstance(arguments, dict):
                raise ProviderError(
                    "streamed tool-call arguments must decode to an object",
                    tool_call_index=index,
                )
        merged.append({"name": state["name"], "arguments": arguments, "id": state["id"]})
    return merged


@dataclass
class RunResult:
    """Everything one execution produced. Serialisable end to end."""

    completion: Completion
    rendered: RenderedPrompt
    prompt_id: str = ""
    prompt_version: int = 1
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    guardrail_events: list[dict] = field(default_factory=list)
    evals: list[EvalResult] = field(default_factory=list)
    fallback_used: str | None = None
    #: What produced this result. Without it, comparing two scores is guesswork —
    #: see assay_core.environment and RESEARCH.md §3.10.
    environment: Any = None
    #: Test-time compute evidence. Empty means one ordinary provider call.
    sampling: dict[str, Any] = field(default_factory=dict)
    #: Delivery evidence. Empty means the non-streaming runtime was used.
    streaming: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.completion.text

    @property
    def cost_usd(self) -> float:
        return self.completion.cost_usd

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "model": self.completion.model,
            "provider": self.completion.provider,
            "output": self.completion.text,
            "tool_calls": self.completion.tool_calls,
            "usage": self.completion.to_dict()["usage"],
            "latency_ms": self.completion.latency_ms,
            "cost_usd": self.completion.cost_usd,
            "fallback_used": self.fallback_used,
            "environment": self.environment.to_dict() if self.environment else None,
            "guardrail_events": self.guardrail_events,
            "sampling": self.sampling,
            "streaming": self.streaming,
            "evals": [
                {"evaluator": e.evaluator, "passed": e.passed, "score": e.score, "reason": e.reason}
                for e in self.evals
            ],
            "rendered": [m.to_dict() for m in self.rendered.messages],
        }


@dataclass
class StreamEvent:
    """A live text/tool-call delta or the final auditable run result."""

    type: str  # delta | tool_call_delta | completed
    index: int
    delta: str = ""
    tool_call: dict[str, Any] | None = None
    buffered: bool = False
    result: RunResult | None = None

    def to_dict(self) -> dict:
        payload: dict[str, Any] = {
            "type": self.type,
            "index": self.index,
            "delta": self.delta,
            "buffered": self.buffered,
        }
        if self.result is not None:
            payload["result"] = self.result.to_dict()
        if self.tool_call is not None:
            payload["tool_call"] = self.tool_call
        return payload


class Runtime:
    """Composes plugins to execute PromptFiles.

    ``Runtime()`` with no arguments works anywhere: it finds the nearest workspace,
    builds a registry, and defaults to the offline ``echo`` provider so that nothing
    in the toolchain requires an API key to be exercised.
    """

    def __init__(
        self,
        *,
        workspace: Workspace | None = None,
        registry: Registry | None = None,
        catalog: ModelCatalog | None = None,
        default_model: str | None = None,
    ) -> None:
        self.workspace = workspace or Workspace.find()
        self.registry = registry or (self.workspace.registry() if self.workspace.is_initialised
                                     else get_registry())
        self.catalog = catalog or ModelCatalog.autoload(self.workspace.root)
        self.default_model = default_model or self.workspace.default_model or "echo/echo"

    # -- render ------------------------------------------------------------

    def render(
        self,
        prompt: PromptFile,
        variables: dict[str, Any] | None = None,
        *,
        model: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> RenderedPrompt:
        variables = dict(variables or {})
        renderer = self.registry.get("assay.renderers", prompt.renderer_id)

        merged_params = {**self.workspace.default_params, **prompt.params, **(params or {})}
        model_ref = model or prompt.model_ref or self.default_model

        messages: list[Message] = []
        for raw in prompt.messages:
            content = raw.get("content")
            if isinstance(content, str):
                content = renderer.render(content, variables, strict=prompt.strict)
            messages.append(Message(
                role=raw.get("role", "user"),
                content=content,
                name=raw.get("name"),
                cache=bool(raw.get("cache")),
                extra={k: v for k, v in raw.items()
                       if k not in {"role", "content", "name", "cache"}},
            ))

        return RenderedPrompt(
            messages=messages,
            model=model_ref,
            params=merged_params,
            provider_params=prompt.provider_params,
            tools=list(prompt.data.get("tools") or []),
            output_schema=prompt.output_schema,
            variables=variables,
            renderer=renderer.id,
        )

    # -- capability gate ---------------------------------------------------

    def check_capabilities(self, prompt: PromptFile, model_ref: str) -> None:
        requires = prompt.data.get("requires") or {}
        required = prompt.required_capabilities
        need_ctx = requires.get("min_context_tokens")
        if not required and not need_ctx:
            return

        provider_id, model_id = parse_model_ref(model_ref)
        info = self.catalog.get(f"{provider_id}/{model_id}")

        if required:
            provider = self.registry.get("assay.providers", provider_id)
            available = set(provider.capabilities(model_id))
            if info and info.capabilities:
                available |= set(info.capabilities)
            missing = sorted(required - available)
            if missing:
                raise CapabilityError(
                    f"{model_ref} cannot satisfy required capabilities: {', '.join(missing)}",
                    prompt_id=prompt.id, model=model_ref,
                    required=sorted(required), available=sorted(available),
                )

        if need_ctx:
            if info is None or not info.context_window:
                raise CapabilityError(
                    f"{model_ref} has no verified context-window metadata; cannot prove "
                    f"the required {need_ctx} tokens",
                    prompt_id=prompt.id, model=model_ref, required_context=int(need_ctx),
                    available_context=None,
                )
            if info.context_window < int(need_ctx):
                raise CapabilityError(
                    f"{model_ref} context window {info.context_window} < required {need_ctx}",
                    prompt_id=prompt.id, model=model_ref,
                    required_context=int(need_ctx), available_context=info.context_window,
                )

    # -- execute -----------------------------------------------------------

    def run(
        self,
        prompt: PromptFile,
        variables: dict[str, Any] | None = None,
        *,
        model: str | None = None,
        params: dict[str, Any] | None = None,
        skip_guardrails: bool = False,
    ) -> RunResult:
        rendered = self.render(prompt, variables, model=model, params=params)
        model_ref = rendered.model or self.default_model
        # Validate the complete fallback set before making the first external call. A
        # configured fallback that cannot honour the artifact contract is not a fallback.
        for candidate in [model_ref, *prompt.fallbacks]:
            self.check_capabilities(prompt, candidate)

        events: list[dict] = []
        if not skip_guardrails:
            rendered = self._apply_input_guardrails(prompt, rendered, events)

        completion, fallback, sampling = self._call_with_sampling(
            prompt, rendered, model_ref
        )

        if not skip_guardrails:
            completion = self._apply_output_guardrails(
                prompt, rendered, completion, model_ref, events
            )

        return self._finish_run(
            prompt,
            rendered,
            completion,
            events=events,
            fallback=fallback,
            sampling=sampling,
        )

    async def arun(
        self,
        prompt: PromptFile,
        variables: dict[str, Any] | None = None,
        *,
        model: str | None = None,
        params: dict[str, Any] | None = None,
        skip_guardrails: bool = False,
    ) -> RunResult:
        """Asynchronously execute one PromptFile without blocking the event loop.

        Providers may implement ``acomplete`` natively. Older third-party providers remain
        compatible: their synchronous ``complete`` method is isolated in a worker thread.
        Sampling stays declaration-ordered so async execution cannot change majority ties or
        verifier selection evidence.
        """
        rendered = self.render(prompt, variables, model=model, params=params)
        model_ref = rendered.model or self.default_model
        for candidate in [model_ref, *prompt.fallbacks]:
            self.check_capabilities(prompt, candidate)

        events: list[dict] = []
        if not skip_guardrails:
            rendered = self._apply_input_guardrails(prompt, rendered, events)

        completion, fallback, sampling = await self._acall_with_sampling(
            prompt, rendered, model_ref
        )

        if not skip_guardrails:
            completion = await self._aapply_output_guardrails(
                prompt, rendered, completion, model_ref, events
            )

        return self._finish_run(
            prompt,
            rendered,
            completion,
            events=events,
            fallback=fallback,
            sampling=sampling,
        )

    async def astream(
        self,
        prompt: PromptFile,
        variables: dict[str, Any] | None = None,
        *,
        model: str | None = None,
        params: dict[str, Any] | None = None,
        skip_guardrails: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        """Stream text and tool-call deltas, then one auditable ``completed`` event.

        Output guardrails force pre-delivery buffering. This intentionally trades time to
        first token for the guarantee that blocked or redacted content is never leaked as a
        partial response. Sampling remains buffered because candidate-selection semantics
        cannot be represented as one live stream. Tool arguments are assembled by stable
        call index and must decode to JSON objects before the run can complete.
        """
        rendered = self.render(prompt, variables, model=model, params=params)
        model_ref = rendered.model or self.default_model
        for candidate in [model_ref, *prompt.fallbacks]:
            self.check_capabilities(prompt, candidate)
        sample_count = int(rendered.params.get("samples", 1) or 1)
        if sample_count != 1:
            raise ProviderError(
                "streaming requires model.params.samples=1; sampled selection is buffered"
            )
        events: list[dict] = []
        if not skip_guardrails:
            rendered = self._apply_input_guardrails(prompt, rendered, events)
        output_gates = [] if skip_guardrails else self._guardrails_for(prompt, "output")

        # A declared output control must see the whole answer before a byte is released.
        if output_gates:
            completion, fallback, chunks, provider_mode = await self._acollect_stream(
                prompt, rendered, model_ref
            )
            completion = await self._aapply_output_guardrails(
                prompt, rendered, completion, model_ref, events
            )
            mode = "buffered_guardrails"
            streaming = {
                "mode": mode,
                "provider_mode": provider_mode,
                "chunks_received": chunks,
                "chunks_delivered": 1 if completion.text else 0,
                "partial_delivery": False,
                "reason": "declared output guardrails require full-output validation",
            }
            result = self._finish_run(
                prompt, rendered, completion, events=events, fallback=fallback, sampling={},
                streaming=streaming,
            )
            index = 0
            if completion.text:
                yield StreamEvent(
                    type="delta", index=index, delta=completion.text, buffered=True
                )
                index += 1
            yield StreamEvent(
                type="completed", index=index, buffered=True, result=result
            )
            return

        attempts = [model_ref, *prompt.fallbacks]
        last_error: Exception | None = None
        for attempt_index, ref in enumerate(attempts):
            provider_id, model_id = parse_model_ref(ref)
            chunks: list[StreamChunk] = []
            delivered = 0
            started = time.perf_counter()
            try:
                provider = self.registry.get("assay.providers", provider_id)
                call = self._provider_prompt(rendered, model_id)
                provider_mode = (
                    "native" if callable(getattr(provider, "astream", None))
                    else "buffered_provider"
                )
                async for chunk in self._bounded_provider_chunks(provider, call):
                    chunks.append(chunk)
                    if chunk.text:
                        yield StreamEvent(
                            type="delta",
                            index=delivered,
                            delta=chunk.text,
                            buffered=provider_mode != "native",
                        )
                        delivered += 1
                    for position, raw_call in enumerate(chunk.tool_calls):
                        yield StreamEvent(
                            type="tool_call_delta",
                            index=delivered,
                            tool_call=_tool_fragment(raw_call, position),
                            buffered=provider_mode != "native",
                        )
                        delivered += 1
                completion = self._completion_from_chunks(
                    chunks,
                    provider_id=provider_id,
                    model_id=model_id,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                )
                fallback = ref if attempt_index else None
                streaming = {
                    "mode": provider_mode,
                    "chunks_received": len(chunks),
                    "chunks_delivered": delivered,
                    "partial_delivery": False,
                }
                result = self._finish_run(
                    prompt, rendered, completion, events=events,
                    fallback=fallback, sampling={}, streaming=streaming,
                )
                yield StreamEvent(
                    type="completed",
                    index=delivered,
                    buffered=provider_mode != "native",
                    result=result,
                )
                return
            except Exception as exc:
                last_error = exc
                if delivered:
                    raise ProviderError(
                        f"{provider_id}: stream failed after partial delivery: {exc}",
                        provider=provider_id,
                        partial_output_delivered=True,
                        chunks_delivered=delivered,
                        attempted=attempts[:attempt_index + 1],
                    ) from exc
                logger.warning("provider %s stream failed for %s: %s", provider_id, ref, exc)
        raise ProviderError(
            f"All models failed for streaming prompt {prompt.id!r}: {last_error}",
            prompt_id=prompt.id,
            attempted=attempts,
            partial_output_delivered=False,
        ) from last_error

    def _finish_run(
        self,
        prompt: PromptFile,
        rendered: RenderedPrompt,
        completion: Completion,
        *,
        events: list[dict],
        fallback: str | None,
        sampling: dict,
        streaming: dict | None = None,
    ) -> RunResult:
        """Create, trace, and audit a result identically for sync and async callers."""
        result = RunResult(
            completion=completion, rendered=rendered,
            prompt_id=prompt.id, prompt_version=prompt.version,
            guardrail_events=events, fallback_used=fallback,
            environment=environment_mod.capture(
                provider=completion.provider, model=completion.model
            ),
            sampling=sampling,
            streaming=dict(streaming or {}),
        )
        self._trace(result)
        self._audit(prompt, result)
        return result

    @staticmethod
    def _provider_prompt(rendered: RenderedPrompt, model_id: str) -> RenderedPrompt:
        return RenderedPrompt(
            messages=rendered.messages,
            model=model_id,
            params={
                key: value for key, value in rendered.params.items()
                if key not in RUNTIME_PARAM_KEYS
            },
            provider_params=rendered.provider_params,
            tools=rendered.tools,
            output_schema=rendered.output_schema,
            variables=rendered.variables,
            renderer=rendered.renderer,
        )

    async def _provider_chunks(
        self, provider: Any, call: RenderedPrompt
    ) -> AsyncIterator[StreamChunk]:
        astream = getattr(provider, "astream", None)
        if callable(astream):
            async for chunk in astream(call):
                if not isinstance(chunk, StreamChunk):
                    raise ProviderError(
                        f"provider {provider.id!r} yielded a non-StreamChunk value"
                    )
                yield chunk
            return

        acomplete = getattr(provider, "acomplete", None)
        if callable(acomplete):
            completion = await acomplete(call)
        else:
            completion = await asyncio.to_thread(provider.complete, call)
        yield StreamChunk(
            text=completion.text,
            model=completion.model,
            provider=completion.provider,
            usage=completion.usage,
            cost_usd=completion.cost_usd,
            finish_reason=completion.finish_reason,
            tool_calls=completion.tool_calls,
            raw=completion.raw,
        )

    async def _bounded_provider_chunks(
        self, provider: Any, call: RenderedPrompt
    ) -> AsyncIterator[StreamChunk]:
        """Enforce provider-neutral stream resource limits before delivering a delta."""
        chunks = 0
        output_bytes = 0
        async for chunk in self._provider_chunks(provider, call):
            chunks += 1
            tool_bytes = len(json.dumps(
                chunk.tool_calls, ensure_ascii=False, default=str, separators=(",", ":")
            ).encode("utf-8")) if chunk.tool_calls else 0
            chunk_bytes = len(chunk.text.encode("utf-8")) + tool_bytes
            output_bytes += chunk_bytes
            if chunks > MAX_STREAM_CHUNKS:
                raise ProviderError(
                    f"provider {provider.id!r} exceeded the {MAX_STREAM_CHUNKS} chunk limit",
                    provider=provider.id,
                    limit="chunks",
                    chunks_received=chunks,
                )
            if chunk_bytes > MAX_STREAM_CHUNK_BYTES:
                raise ProviderError(
                    f"provider {provider.id!r} emitted a stream chunk larger than "
                    f"{MAX_STREAM_CHUNK_BYTES} bytes",
                    provider=provider.id,
                    limit="chunk_bytes",
                    chunk_bytes=chunk_bytes,
                )
            if output_bytes > MAX_STREAM_OUTPUT_BYTES:
                raise ProviderError(
                    f"provider {provider.id!r} exceeded the {MAX_STREAM_OUTPUT_BYTES}-byte "
                    "stream output limit",
                    provider=provider.id,
                    limit="output_bytes",
                    output_bytes=output_bytes,
                )
            yield chunk

    def _completion_from_chunks(
        self,
        chunks: list[StreamChunk],
        *,
        provider_id: str,
        model_id: str,
        elapsed_ms: int,
    ) -> Completion:
        usage = next(
            (chunk.usage for chunk in reversed(chunks) if chunk.usage is not None),
            Usage(),
        )
        finish_reason = next(
            (chunk.finish_reason for chunk in reversed(chunks) if chunk.finish_reason),
            None,
        )
        model = next((chunk.model for chunk in reversed(chunks) if chunk.model), model_id)
        provider = next(
            (chunk.provider for chunk in reversed(chunks) if chunk.provider), provider_id
        )
        cost = next(
            (chunk.cost_usd for chunk in reversed(chunks) if chunk.cost_usd is not None),
            0.0,
        )
        tool_calls = _merge_stream_tool_calls(chunks)
        return Completion(
            text="".join(chunk.text for chunk in chunks),
            model=model,
            provider=provider,
            usage=usage,
            latency_ms=elapsed_ms,
            cost_usd=cost,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            raw={"stream_chunks": len(chunks)},
        )

    async def _acollect_stream(
        self,
        prompt: PromptFile,
        rendered: RenderedPrompt,
        model_ref: str,
    ) -> tuple[Completion, str | None, int, str]:
        attempts = [model_ref, *prompt.fallbacks]
        last_error: Exception | None = None
        for index, ref in enumerate(attempts):
            provider_id, model_id = parse_model_ref(ref)
            chunks: list[StreamChunk] = []
            started = time.perf_counter()
            try:
                provider = self.registry.get("assay.providers", provider_id)
                call = self._provider_prompt(rendered, model_id)
                mode = (
                    "native" if callable(getattr(provider, "astream", None))
                    else "buffered_provider"
                )
                async for chunk in self._bounded_provider_chunks(provider, call):
                    chunks.append(chunk)
                return (
                    self._completion_from_chunks(
                        chunks,
                        provider_id=provider_id,
                        model_id=model_id,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                    ),
                    ref if index else None,
                    len(chunks),
                    mode,
                )
            except Exception as exc:
                last_error = exc
                logger.warning("provider %s stream failed for %s: %s", provider_id, ref, exc)
        raise ProviderError(
            f"All models failed for streaming prompt {prompt.id!r}: {last_error}",
            prompt_id=prompt.id,
            attempted=attempts,
            partial_output_delivered=False,
        ) from last_error

    def _call_with_sampling(
        self,
        prompt: PromptFile,
        rendered: RenderedPrompt,
        model_ref: str,
    ) -> tuple[Completion, str | None, dict]:
        """Execute bounded test-time samples and select one without hiding total spend."""
        sample_count = int(rendered.params.get("samples", 1) or 1)
        if sample_count < 1 or sample_count > 16:
            raise ProviderError("model.params.samples must be between 1 and 16")
        selection = str(rendered.params.get("selection", "majority"))
        verifier_ref = rendered.params.get("verifier")
        provider_params = {
            key: value for key, value in rendered.params.items()
            if key not in SELECTION_PARAM_KEYS
        }
        call = RenderedPrompt(
            messages=rendered.messages,
            model=rendered.model,
            params=provider_params,
            provider_params=rendered.provider_params,
            tools=rendered.tools,
            output_schema=rendered.output_schema,
            variables=rendered.variables,
            renderer=rendered.renderer,
        )

        candidates: list[Completion] = []
        fallbacks: list[str | None] = []
        for _ in range(sample_count):
            completion, fallback = self._call_with_fallbacks(prompt, call, model_ref)
            candidates.append(completion)
            fallbacks.append(fallback)

        if sample_count == 1:
            return candidates[0], fallbacks[0], {}

        verifier_runs: list[RunResult] = []
        keys = [_candidate_key(candidate) for candidate in candidates]
        if selection == "majority":
            counts = {key: keys.count(key) for key in set(keys)}
            selected_index = max(range(sample_count), key=lambda i: counts[keys[i]])
            selection_detail = {
                "agreement": round(counts[keys[selected_index]] / sample_count, 6),
                "vote_counts": sorted(counts.values(), reverse=True),
            }
        elif selection == "verifier":
            if not isinstance(verifier_ref, str) or not verifier_ref:
                raise ProviderError(
                    "model.params.selection='verifier' requires model.params.verifier"
                )
            scores = []
            reasons = []
            for candidate in candidates:
                score, reason, verifier_run = self._score_with_verifier(
                    verifier_ref, prompt, candidate.text, model_ref
                )
                scores.append(score)
                reasons.append(reason)
                verifier_runs.append(verifier_run)
            selected_index = max(range(sample_count), key=lambda i: scores[i])
            selection_detail = {
                "verifier": verifier_ref,
                "scores": scores,
                "selected_reason": reasons[selected_index],
            }
        else:
            raise ProviderError(
                f"unknown sample selection {selection!r}; use 'majority' or 'verifier'"
            )

        selected = copy.deepcopy(candidates[selected_index])
        all_completions = [*candidates, *(run.completion for run in verifier_runs)]
        selected.usage = Usage(
            input_tokens=sum(item.usage.input_tokens for item in all_completions),
            output_tokens=sum(item.usage.output_tokens for item in all_completions),
            cached_input_tokens=sum(item.usage.cached_input_tokens for item in all_completions),
            reasoning_tokens=sum(item.usage.reasoning_tokens for item in all_completions),
        )
        selected.cost_usd = sum(item.cost_usd for item in all_completions)
        selected.latency_ms = sum(item.latency_ms for item in all_completions)
        first_cost = candidates[0].cost_usd
        sampling = {
            "samples_requested": sample_count,
            "samples_usable": len(candidates),
            "selection": selection,
            "selected_index": selected_index,
            "single_sample_cost_usd": first_cost,
            "total_cost_usd": selected.cost_usd,
            "cost_multiplier": (
                round(selected.cost_usd / first_cost, 6) if first_cost > 0 else None
            ),
            "candidates": [
                {
                    "index": index,
                    "output_sha256": hashlib.sha256(
                        candidate.text.encode("utf-8")
                    ).hexdigest(),
                    "cost_usd": candidate.cost_usd,
                    "latency_ms": candidate.latency_ms,
                    "selected": index == selected_index,
                }
                for index, candidate in enumerate(candidates)
            ],
            **selection_detail,
        }
        selected.raw = {**selected.raw, "sampling": sampling}
        return selected, fallbacks[selected_index], sampling

    def _score_with_verifier(
        self,
        verifier_ref: str,
        original: PromptFile,
        candidate: str,
        model_ref: str,
    ) -> tuple[float, str, RunResult]:
        verifier = self.workspace.store().get(verifier_ref)
        if verifier.kind != "prompt":
            raise ProviderError("sample verifier must be kind: prompt")
        run = self.run(
            verifier,
            {"candidate": candidate, "prompt_id": original.id},
            params={"samples": 1},
        )
        text = run.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
            score = float(payload["score"])
            reason = str(payload.get("reason", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(
                f"sample verifier {verifier_ref!r} returned invalid JSON score: {exc}"
            ) from exc
        if not 0.0 <= score <= 1.0:
            raise ProviderError(
                f"sample verifier {verifier_ref!r} score {score} is outside 0..1"
            )
        return score, reason, run

    async def _acall_with_sampling(
        self,
        prompt: PromptFile,
        rendered: RenderedPrompt,
        model_ref: str,
    ) -> tuple[Completion, str | None, dict]:
        """Async equivalent of ``_call_with_sampling`` with stable call ordering."""
        sample_count = int(rendered.params.get("samples", 1) or 1)
        if sample_count < 1 or sample_count > 16:
            raise ProviderError("model.params.samples must be between 1 and 16")
        selection = str(rendered.params.get("selection", "majority"))
        verifier_ref = rendered.params.get("verifier")
        provider_params = {
            key: value for key, value in rendered.params.items()
            if key not in SELECTION_PARAM_KEYS
        }
        call = RenderedPrompt(
            messages=rendered.messages,
            model=rendered.model,
            params=provider_params,
            provider_params=rendered.provider_params,
            tools=rendered.tools,
            output_schema=rendered.output_schema,
            variables=rendered.variables,
            renderer=rendered.renderer,
        )

        candidates: list[Completion] = []
        fallbacks: list[str | None] = []
        # Keep samples sequential. ``aevaluate`` supplies the global bounded fan-out;
        # multiplying it here would violate the advertised provider-call ceiling.
        for _ in range(sample_count):
            completion, fallback = await self._acall_with_fallbacks(
                prompt, call, model_ref
            )
            candidates.append(completion)
            fallbacks.append(fallback)

        if sample_count == 1:
            return candidates[0], fallbacks[0], {}

        verifier_runs: list[RunResult] = []
        keys = [_candidate_key(candidate) for candidate in candidates]
        if selection == "majority":
            counts = {key: keys.count(key) for key in set(keys)}
            selected_index = max(range(sample_count), key=lambda i: counts[keys[i]])
            selection_detail = {
                "agreement": round(counts[keys[selected_index]] / sample_count, 6),
                "vote_counts": sorted(counts.values(), reverse=True),
            }
        elif selection == "verifier":
            if not isinstance(verifier_ref, str) or not verifier_ref:
                raise ProviderError(
                    "model.params.selection='verifier' requires model.params.verifier"
                )
            scores: list[float] = []
            reasons: list[str] = []
            for candidate in candidates:
                score, reason, verifier_run = await self._ascore_with_verifier(
                    verifier_ref, prompt, candidate.text, model_ref
                )
                scores.append(score)
                reasons.append(reason)
                verifier_runs.append(verifier_run)
            selected_index = max(range(sample_count), key=lambda i: scores[i])
            selection_detail = {
                "verifier": verifier_ref,
                "scores": scores,
                "selected_reason": reasons[selected_index],
            }
        else:
            raise ProviderError(
                f"unknown sample selection {selection!r}; use 'majority' or 'verifier'"
            )

        selected = copy.deepcopy(candidates[selected_index])
        all_completions = [*candidates, *(run.completion for run in verifier_runs)]
        selected.usage = Usage(
            input_tokens=sum(item.usage.input_tokens for item in all_completions),
            output_tokens=sum(item.usage.output_tokens for item in all_completions),
            cached_input_tokens=sum(item.usage.cached_input_tokens for item in all_completions),
            reasoning_tokens=sum(item.usage.reasoning_tokens for item in all_completions),
        )
        selected.cost_usd = sum(item.cost_usd for item in all_completions)
        selected.latency_ms = sum(item.latency_ms for item in all_completions)
        first_cost = candidates[0].cost_usd
        sampling = {
            "samples_requested": sample_count,
            "samples_usable": len(candidates),
            "selection": selection,
            "selected_index": selected_index,
            "single_sample_cost_usd": first_cost,
            "total_cost_usd": selected.cost_usd,
            "cost_multiplier": (
                round(selected.cost_usd / first_cost, 6) if first_cost > 0 else None
            ),
            "candidates": [
                {
                    "index": index,
                    "output_sha256": hashlib.sha256(
                        candidate.text.encode("utf-8")
                    ).hexdigest(),
                    "cost_usd": candidate.cost_usd,
                    "latency_ms": candidate.latency_ms,
                    "selected": index == selected_index,
                }
                for index, candidate in enumerate(candidates)
            ],
            **selection_detail,
        }
        selected.raw = {**selected.raw, "sampling": sampling}
        return selected, fallbacks[selected_index], sampling

    async def _ascore_with_verifier(
        self,
        verifier_ref: str,
        original: PromptFile,
        candidate: str,
        model_ref: str,
    ) -> tuple[float, str, RunResult]:
        verifier = self.workspace.store().get(verifier_ref)
        if verifier.kind != "prompt":
            raise ProviderError("sample verifier must be kind: prompt")
        run = await self.arun(
            verifier,
            {"candidate": candidate, "prompt_id": original.id},
            params={"samples": 1},
        )
        text = run.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
            score = float(payload["score"])
            reason = str(payload.get("reason", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(
                f"sample verifier {verifier_ref!r} returned invalid JSON score: {exc}"
            ) from exc
        if not 0.0 <= score <= 1.0:
            raise ProviderError(
                f"sample verifier {verifier_ref!r} score {score} is outside 0..1"
            )
        return score, reason, run

    def _call_with_fallbacks(
        self, prompt: PromptFile, rendered: RenderedPrompt, model_ref: str
    ) -> tuple[Completion, str | None]:
        attempts = [model_ref, *prompt.fallbacks]
        last_error: Exception | None = None
        retry_events: list[dict[str, Any]] = []
        policy = self._rate_limit_policy(rendered.params)
        for index, ref in enumerate(attempts):
            provider_id, model_id = parse_model_ref(ref)
            try:
                provider = self.registry.get("assay.providers", provider_id)
                call = RenderedPrompt(
                    messages=rendered.messages, model=model_id,
                    params={k: v for k, v in rendered.params.items()
                            if k not in RUNTIME_PARAM_KEYS},
                    provider_params=rendered.provider_params, tools=rendered.tools,
                    output_schema=rendered.output_schema, variables=rendered.variables,
                    renderer=rendered.renderer,
                )
                waited = 0.0
                for retry_index in range(policy["retries"] + 1):
                    try:
                        completion = provider.complete(call)
                        break
                    except RateLimitError as exc:
                        if retry_index >= policy["retries"]:
                            raise
                        delay, source = self._rate_limit_delay(
                            exc, retry_index=retry_index, waited=waited, policy=policy
                        )
                        retry_events.append({
                            "provider": provider_id, "model": model_id,
                            "retry": retry_index + 1,
                            "wait_ms": round(delay * 1000), "source": source,
                        })
                        if delay:
                            time.sleep(delay)
                        waited += delay
                self._attach_rate_limit_evidence(completion, retry_events)
                return completion, (ref if index else None)
            except Exception as exc:
                last_error = exc
                logger.warning("provider %s failed for %s: %s", provider_id, ref, exc)
        raise ProviderError(
            f"All models failed for prompt {prompt.id!r}: {last_error}",
            prompt_id=prompt.id, attempted=attempts, rate_limit_retries=retry_events,
        ) from last_error

    async def _acall_with_fallbacks(
        self, prompt: PromptFile, rendered: RenderedPrompt, model_ref: str
    ) -> tuple[Completion, str | None]:
        attempts = [model_ref, *prompt.fallbacks]
        last_error: Exception | None = None
        retry_events: list[dict[str, Any]] = []
        policy = self._rate_limit_policy(rendered.params)
        for index, ref in enumerate(attempts):
            provider_id, model_id = parse_model_ref(ref)
            try:
                provider = self.registry.get("assay.providers", provider_id)
                call = RenderedPrompt(
                    messages=rendered.messages, model=model_id,
                    params={k: v for k, v in rendered.params.items()
                            if k not in RUNTIME_PARAM_KEYS},
                    provider_params=rendered.provider_params, tools=rendered.tools,
                    output_schema=rendered.output_schema, variables=rendered.variables,
                    renderer=rendered.renderer,
                )
                waited = 0.0
                for retry_index in range(policy["retries"] + 1):
                    try:
                        acomplete = getattr(provider, "acomplete", None)
                        if callable(acomplete):
                            completion = await acomplete(call)
                        else:
                            completion = await asyncio.to_thread(provider.complete, call)
                        break
                    except RateLimitError as exc:
                        if retry_index >= policy["retries"]:
                            raise
                        delay, source = self._rate_limit_delay(
                            exc, retry_index=retry_index, waited=waited, policy=policy
                        )
                        retry_events.append({
                            "provider": provider_id, "model": model_id,
                            "retry": retry_index + 1,
                            "wait_ms": round(delay * 1000), "source": source,
                        })
                        if delay:
                            await asyncio.sleep(delay)
                        waited += delay
                self._attach_rate_limit_evidence(completion, retry_events)
                return completion, (ref if index else None)
            except Exception as exc:
                last_error = exc
                logger.warning("provider %s failed for %s: %s", provider_id, ref, exc)
        raise ProviderError(
            f"All models failed for prompt {prompt.id!r}: {last_error}",
            prompt_id=prompt.id, attempted=attempts, rate_limit_retries=retry_events,
        ) from last_error

    @staticmethod
    def _rate_limit_policy(params: dict[str, Any]) -> dict[str, float | int]:
        raw_retries = params.get("rate_limit_retries", 2)
        raw_backoff = params.get("rate_limit_backoff_s", 0.5)
        raw_max_wait = params.get("rate_limit_max_wait_s", 30.0)
        if (
            isinstance(raw_retries, bool) or not isinstance(raw_retries, int)
            or not 0 <= raw_retries <= 5
        ):
            raise ProviderError("model.params.rate_limit_retries must be an integer from 0 to 5")
        for name, value, maximum in (
            ("rate_limit_backoff_s", raw_backoff, 10.0),
            ("rate_limit_max_wait_s", raw_max_wait, 60.0),
        ):
            if (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not 0 <= float(value) <= maximum
            ):
                raise ProviderError(
                    f"model.params.{name} must be a number from 0 to {maximum:g}"
                )
        return {
            "retries": raw_retries,
            "backoff_s": float(raw_backoff),
            "max_wait_s": float(raw_max_wait),
        }

    @staticmethod
    def _rate_limit_delay(
        error: RateLimitError, *, retry_index: int, waited: float,
        policy: dict[str, float | int],
    ) -> tuple[float, str]:
        retry_after = error.context.get("retry_after")
        requested: float | None = None
        source = "exponential_backoff"
        if retry_after not in (None, ""):
            try:
                requested = max(0.0, float(retry_after))
                source = "retry_after_seconds"
            except (TypeError, ValueError):
                try:
                    moment = parsedate_to_datetime(str(retry_after))
                    if moment.tzinfo is None:
                        moment = moment.replace(tzinfo=timezone.utc)
                    requested = max(
                        0.0, (moment - datetime.now(timezone.utc)).total_seconds()
                    )
                    source = "retry_after_date"
                except (TypeError, ValueError, OverflowError):
                    requested = None
        if requested is None:
            requested = float(policy["backoff_s"]) * (2 ** retry_index)
        remaining = max(0.0, float(policy["max_wait_s"]) - waited)
        return min(requested, remaining), source

    @staticmethod
    def _attach_rate_limit_evidence(
        completion: Completion, events: list[dict[str, Any]]
    ) -> None:
        if not events:
            return
        total_wait_ms = sum(int(event["wait_ms"]) for event in events)
        completion.latency_ms += total_wait_ms
        completion.raw = {
            **completion.raw,
            "rate_limit": {
                "retries": len(events),
                "wait_ms": total_wait_ms,
                "events": list(events),
            },
        }

    # -- guardrails --------------------------------------------------------

    def _guardrails_for(self, prompt: PromptFile, stage: str) -> list[tuple[Any, dict]]:
        selected = []
        for spec in prompt.guardrails:
            configured = spec.get("stage", "output")
            if configured not in (stage, "both"):
                continue
            try:
                plugin = self.registry.get("assay.guardrails", spec["type"])
            except Exception as exc:
                raise GuardrailViolation(
                    f"Configured guardrail {spec.get('type')!r} is unavailable; refusing "
                    "to run without a declared control",
                    prompt_id=prompt.id, guardrail=spec.get("type"), stage=stage,
                ) from exc
            selected.append((plugin, spec))
        return selected

    def _apply_input_guardrails(
        self, prompt: PromptFile, rendered: RenderedPrompt, events: list[dict]
    ) -> RenderedPrompt:
        for plugin, spec in self._guardrails_for(prompt, "input"):
            config = {**(spec.get("config") or {}), "action": spec.get("action", "block")}
            for message in rendered.messages:
                if not isinstance(message.content, str):
                    continue
                verdict = plugin.check(message.content, config=config, stage="input",
                                       context={"prompt_id": prompt.id})
                if verdict.allowed:
                    continue
                events.append({"stage": "input", "guardrail": verdict.guardrail,
                               "action": verdict.action, "reason": verdict.reason})
                if verdict.action == "block":
                    raise GuardrailViolation(
                        f"Input blocked by {verdict.guardrail}: {verdict.reason}",
                        prompt_id=prompt.id, guardrail=verdict.guardrail,
                    )
                if verdict.action == "redact" and verdict.transformed is not None:
                    message.content = verdict.transformed
        return rendered

    def _apply_output_guardrails(
        self,
        prompt: PromptFile,
        rendered: RenderedPrompt,
        completion: Completion,
        model_ref: str,
        events: list[dict],
        _retries: int = 0,
    ) -> Completion:
        for plugin, spec in self._guardrails_for(prompt, "output"):
            config = {**(spec.get("config") or {}), "action": spec.get("action", "block")}
            verdict = plugin.check(
                completion.text, config=config, stage="output",
                context={"prompt_id": prompt.id, "output_schema": prompt.output_schema},
            )
            if verdict.allowed:
                continue
            events.append({"stage": "output", "guardrail": verdict.guardrail,
                           "action": verdict.action, "reason": verdict.reason,
                           "retry": _retries})
            if verdict.action == "block":
                raise GuardrailViolation(
                    f"Output blocked by {verdict.guardrail}: {verdict.reason}",
                    prompt_id=prompt.id, guardrail=verdict.guardrail,
                )
            if verdict.action == "redact" and verdict.transformed is not None:
                completion.text = verdict.transformed
            elif verdict.action == "retry" and _retries < MAX_GUARDRAIL_RETRIES:
                repaired = RenderedPrompt(
                    messages=[*rendered.messages,
                              Message(role="assistant", content=completion.text),
                              Message(role="user",
                                      content=REPAIR_INSTRUCTION.format(reason=verdict.reason))],
                    model=rendered.model, params=rendered.params,
                    provider_params=rendered.provider_params, tools=rendered.tools,
                    output_schema=rendered.output_schema, variables=rendered.variables,
                )
                retry_completion, _ = self._call_with_fallbacks(prompt, repaired, model_ref)
                return self._apply_output_guardrails(
                    prompt, rendered, retry_completion, model_ref, events, _retries + 1
                )
        return completion

    async def _aapply_output_guardrails(
        self,
        prompt: PromptFile,
        rendered: RenderedPrompt,
        completion: Completion,
        model_ref: str,
        events: list[dict],
        _retries: int = 0,
    ) -> Completion:
        """Async output gate; retry calls use the same async provider path."""
        for plugin, spec in self._guardrails_for(prompt, "output"):
            config = {**(spec.get("config") or {}), "action": spec.get("action", "block")}
            verdict = plugin.check(
                completion.text, config=config, stage="output",
                context={"prompt_id": prompt.id, "output_schema": prompt.output_schema},
            )
            if verdict.allowed:
                continue
            events.append({"stage": "output", "guardrail": verdict.guardrail,
                           "action": verdict.action, "reason": verdict.reason,
                           "retry": _retries})
            if verdict.action == "block":
                raise GuardrailViolation(
                    f"Output blocked by {verdict.guardrail}: {verdict.reason}",
                    prompt_id=prompt.id, guardrail=verdict.guardrail,
                )
            if verdict.action == "redact" and verdict.transformed is not None:
                completion.text = verdict.transformed
            elif verdict.action == "retry" and _retries < MAX_GUARDRAIL_RETRIES:
                repaired = RenderedPrompt(
                    messages=[*rendered.messages,
                              Message(role="assistant", content=completion.text),
                              Message(role="user",
                                      content=REPAIR_INSTRUCTION.format(reason=verdict.reason))],
                    model=rendered.model, params=rendered.params,
                    provider_params=rendered.provider_params, tools=rendered.tools,
                    output_schema=rendered.output_schema, variables=rendered.variables,
                )
                retry_completion, _ = await self._acall_with_fallbacks(
                    prompt, repaired, model_ref
                )
                return await self._aapply_output_guardrails(
                    prompt, rendered, retry_completion, model_ref, events, _retries + 1
                )
        return completion

    # -- evaluation --------------------------------------------------------

    def evaluate(
        self,
        prompt: PromptFile,
        *,
        cases: list[dict] | None = None,
        model: str | None = None,
        judge_model: str | None = None,
    ) -> dict:
        """Run every embedded eval case and roll the results up.

        Returns a dict shaped for CI consumption: ``passed`` gates the exit code.
        """
        started = time.perf_counter()
        cases = resolve_eval_cases(
            prompt,
            cases if cases is not None else prompt.evals,
            workspace_root=self.workspace.root,
        )
        case_reports: list[dict] = []
        all_results: list[EvalResult] = []
        grouped_results: list[tuple[str, list[EvalResult]]] = []

        for case in cases:
            variables = case.get("input") or {}
            try:
                run = self.run(prompt, variables, model=model)
            except Exception as exc:
                failure = EvalResult(passed=False, score=0.0, evaluator="runtime",
                                     reason=f"execution failed: {exc}")
                all_results.append(failure)
                case_id = str(case.get("id", "?"))
                grouped_results.append((case_id, [failure]))
                case_reports.append({"id": case_id, "passed": False,
                                     "error": str(exc), "results": []})
                continue

            context = {
                "cost_usd": run.cost_usd,
                "latency_ms": run.completion.latency_ms,
                "output_schema": prompt.output_schema,
                "expected_output": case.get("expected_output"),
                "judge": self._make_judge(judge_model or model),
            }
            results = self._evaluate_assertions(
                run.text, case.get("assert") or [], context
            )
            run.evals = results
            all_results.extend(results)
            case_id = str(case.get("id", "?"))
            grouped_results.append((case_id, results))
            summary = aggregate(results)
            case_reports.append({
                "id": case_id,
                "passed": summary["passed"],
                "score": summary["score"],
                "output": run.text,
                "cost_usd": run.cost_usd,
                "latency_ms": run.completion.latency_ms,
                "sampling": run.sampling,
                "samples_requested": run.sampling.get("samples_requested", 1),
                "selection": run.sampling.get("selection", "single"),
                "single_sample_cost_usd": run.sampling.get(
                    "single_sample_cost_usd", run.cost_usd
                ),
                "results": [
                    {"evaluator": r.evaluator, "passed": r.passed,
                     "score": r.score, "reason": r.reason, "details": r.details}
                    for r in results
                ],
            })

        unverified_cases = sum(1 for case in case_reports if case.get("passed") is None)
        overall = aggregate(all_results, unverified=unverified_cases)
        score_ci = score_confidence_interval(
            [results for _, results in grouped_results],
            unverified_cases=unverified_cases,
        )
        provider = ""
        if case_reports:
            provider = (model or prompt.model_ref or self.default_model).split("/")[0]
        return {
            "prompt_id": prompt.id,
            "prompt_version": prompt.version,
            "model": model or prompt.model_ref or self.default_model,
            "environment": environment_mod.capture(
                provider=provider, model=model or prompt.model_ref or self.default_model
            ).to_dict(),
            "passed": overall["passed"],
            "score": overall["score"],
            "score_ci": score_ci,
            "usable": overall["usable"],
            "cases": case_reports,
            "total_assertions": overall["total"],
            "failed_assertions": overall["failed"],
            "unverified_cases": unverified_cases,
            "failure_attribution": failure_attribution(grouped_results),
            "total_cost_usd": round(sum(c.get("cost_usd", 0) for c in case_reports), 6),
            "accuracy_cost": accuracy_cost_report(overall["score"], case_reports),
            "execution": {
                "mode": "serial",
                "max_concurrency": 1,
                "scheduled_cases": len(cases),
                "wallclock_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        }

    async def aevaluate(
        self,
        prompt: PromptFile,
        *,
        cases: list[dict] | None = None,
        model: str | None = None,
        judge_model: str | None = None,
        max_concurrency: int = 4,
    ) -> dict:
        """Evaluate cases concurrently with a hard provider-call concurrency ceiling.

        Results are always returned in declaration order. A case retains the semaphore
        while it runs its completion, assertions, and any judge call, so nested work cannot
        silently exceed ``max_concurrency``. Test-time samples within one case remain serial.
        """
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int):
            raise ValueError("max_concurrency must be an integer")
        if not 1 <= max_concurrency <= 32:
            raise ValueError("max_concurrency must be between 1 and 32")

        started = time.perf_counter()
        resolved = resolve_eval_cases(
            prompt,
            cases if cases is not None else prompt.evals,
            workspace_root=self.workspace.root,
        )
        active_limit = min(max_concurrency, max(len(resolved), 1))
        semaphore = asyncio.Semaphore(active_limit)

        async def evaluate_case(case: dict) -> tuple[dict, tuple[str, list[EvalResult]]]:
            async with semaphore:
                variables = case.get("input") or {}
                case_id = str(case.get("id", "?"))
                try:
                    run = await self.arun(prompt, variables, model=model)
                except Exception as exc:
                    failure = EvalResult(
                        passed=False, score=0.0, evaluator="runtime",
                        reason=f"execution failed: {exc}",
                    )
                    return (
                        {"id": case_id, "passed": False, "error": str(exc), "results": []},
                        (case_id, [failure]),
                    )

                context = {
                    "cost_usd": run.cost_usd,
                    "latency_ms": run.completion.latency_ms,
                    "output_schema": prompt.output_schema,
                    "expected_output": case.get("expected_output"),
                    "judge": self._make_judge(judge_model or model),
                }
                # Evaluator plugins are synchronous by contract. Running the complete
                # assertion set in a worker also keeps an llm_judge call off the event loop.
                results = await asyncio.to_thread(
                    self._evaluate_assertions,
                    run.text,
                    case.get("assert") or [],
                    context,
                )
                run.evals = results
                summary = aggregate(results)
                report = {
                    "id": case_id,
                    "passed": summary["passed"],
                    "score": summary["score"],
                    "output": run.text,
                    "cost_usd": run.cost_usd,
                    "latency_ms": run.completion.latency_ms,
                    "sampling": run.sampling,
                    "samples_requested": run.sampling.get("samples_requested", 1),
                    "selection": run.sampling.get("selection", "single"),
                    "single_sample_cost_usd": run.sampling.get(
                        "single_sample_cost_usd", run.cost_usd
                    ),
                    "results": [
                        {"evaluator": result.evaluator, "passed": result.passed,
                         "score": result.score, "reason": result.reason,
                         "details": result.details}
                        for result in results
                    ],
                }
                return report, (case_id, results)

        completed = await asyncio.gather(*(evaluate_case(case) for case in resolved))
        case_reports = [item[0] for item in completed]
        grouped_results = [item[1] for item in completed]
        all_results = [result for _, results in grouped_results for result in results]
        unverified_cases = sum(1 for case in case_reports if case.get("passed") is None)
        overall = aggregate(all_results, unverified=unverified_cases)
        score_ci = score_confidence_interval(
            [results for _, results in grouped_results],
            unverified_cases=unverified_cases,
        )
        provider = ""
        if case_reports:
            provider = (model or prompt.model_ref or self.default_model).split("/")[0]
        return {
            "prompt_id": prompt.id,
            "prompt_version": prompt.version,
            "model": model or prompt.model_ref or self.default_model,
            "environment": environment_mod.capture(
                provider=provider, model=model or prompt.model_ref or self.default_model
            ).to_dict(),
            "passed": overall["passed"],
            "score": overall["score"],
            "score_ci": score_ci,
            "usable": overall["usable"],
            "cases": case_reports,
            "total_assertions": overall["total"],
            "failed_assertions": overall["failed"],
            "unverified_cases": unverified_cases,
            "failure_attribution": failure_attribution(grouped_results),
            "total_cost_usd": round(sum(c.get("cost_usd", 0) for c in case_reports), 6),
            "accuracy_cost": accuracy_cost_report(overall["score"], case_reports),
            "execution": {
                "mode": "bounded_concurrent",
                "max_concurrency": active_limit,
                "scheduled_cases": len(resolved),
                "wallclock_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        }

    def _evaluate_assertions(
        self,
        output: str,
        assertions: list[dict],
        context: dict[str, Any],
    ) -> list[EvalResult]:
        results: list[EvalResult] = []
        for assertion in assertions:
            try:
                evaluator = self.registry.get("assay.evaluators", assertion["type"])
                results.append(
                    evaluator.evaluate(output, assertion=assertion, context=context)
                )
            except Exception as exc:
                results.append(EvalResult(
                    passed=False, score=0.0, evaluator=assertion.get("type", "?"),
                    reason=f"evaluator error: {exc}",
                ))
        return results

    def _make_judge(self, model_ref: str | None) -> Callable[[str], str]:
        """Build the callable that ``llm_judge`` uses, so evaluators stay provider-agnostic."""
        ref = model_ref or self.default_model

        def judge(text: str) -> str:
            provider_id, model_id = parse_model_ref(ref)
            provider = self.registry.get("assay.providers", provider_id)
            call = RenderedPrompt(
                messages=[Message(role="user", content=text)],
                model=model_id, params={"temperature": 0},
            )
            return provider.complete(call).text

        return judge

    def _audit(self, prompt: PromptFile, result: RunResult) -> None:
        """Append a run record when the workspace asks for one.

        Off unless ``governance.audit: true`` — an audit log nobody configured is a
        surprise file appearing in someone's repository, and content is excluded even
        then unless explicitly requested.
        """
        config = dict(self.workspace.config.get("governance") or {})
        if not config.get("audit"):
            return
        try:
            from .governance import AuditLog, AuditRecord

            record = AuditRecord(
                run_id=result.run_id,
                artifact_id=prompt.id,
                kind=prompt.kind,
                version=prompt.version,
                outcome="completed",
                model=result.completion.model,
                provider=result.completion.provider,
                cost_usd=result.cost_usd,
                total_tokens=result.completion.usage.total_tokens,
                latency_ms=result.completion.latency_ms,
                environment=result.environment.fingerprint if result.environment else "",
                actor=config.get("actor", ""),
                deployment_id=(
                    config.get("deployment_id") or os.getenv("ASSAY_DEPLOYMENT_ID", "")
                ),
                streaming=dict(result.streaming) if result.streaming else None,
            )
            if config.get("log_content"):
                record.content = {
                    "rendered": result.rendered.text[:8000],
                    "output": result.completion.text[:8000],
                }
            AuditLog(
                config.get("audit_root") or (self.workspace.root / ".assay" / "audit"),
                retention_days=int(config.get("retention_days", 190)),
            ).append(record)
        except Exception as exc:  # auditing must never break execution
            logger.warning("audit log write failed: %s", exc)

    # -- tracing -----------------------------------------------------------

    def _trace(self, result: RunResult) -> None:
        for record in self.registry.records("assay.tracers"):
            try:
                tracer = self.registry.get("assay.tracers", record.name)
                tracer.on_run(
                    prompt=result.rendered, completion=result.completion,
                    meta={"prompt_id": result.prompt_id, "run_id": result.run_id,
                          "prompt_version": result.prompt_version,
                          "streaming": dict(result.streaming)},
                )
            except Exception as exc:  # tracing must never break execution
                logger.debug("tracer %s failed: %s", record.name, exc)

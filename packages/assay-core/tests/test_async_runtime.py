"""Async runtime and bounded evaluation contracts.

These tests prove overlap and ceilings structurally. A timing-only test could stay green on
a fast serial implementation, which would violate the repository's mutation rule.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import assay_core.runtime as runtime_module

from assay_core import (
    Completion,
    PromptFile,
    ProviderError,
    Registry,
    Runtime,
    StreamChunk,
    Usage,
    Workspace,
)
from assay_core.builtins.providers import (
    AnthropicProvider,
    GoogleProvider,
    OllamaProvider,
    OpenAIProvider,
)
from assay_core.builtins import providers as providers_module
from assay_core.contracts import CONTRACT_VERSION, Message, RenderedPrompt
from assay_core.errors import RateLimitError


ASYNC_EVAL = """---
promptfile: 1
id: async/eval
model: {primary: async_probe/model}
evals:
  - {id: first, input: {label: first, delay: 0.04}, assert: [{type: contains, value: first}]}
  - {id: second, input: {label: second, delay: 0.01}, assert: [{type: contains, value: second}]}
  - {id: third, input: {label: third, delay: 0.02}, assert: [{type: contains, value: third}]}
  - {id: fourth, input: {label: fourth, delay: 0.01}, assert: [{type: contains, value: fourth}]}
---
{{ label }}
"""


class AsyncProbeProvider:
    id = "async_probe"
    contract_version = CONTRACT_VERSION

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.calls: list[str] = []
        self.two_active = asyncio.Event()

    def capabilities(self, model: str) -> frozenset[str]:
        return frozenset({"text"})

    def list_models(self):
        return []

    def complete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        raise AssertionError("native async provider was routed through complete")

    async def acomplete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        label = str(prompt.variables["label"])
        self.calls.append(label)
        self.active += 1
        self.peak = max(self.peak, self.active)
        if self.active >= 2:
            self.two_active.set()
        try:
            # The first call requires genuine overlap. A serial implementation times out.
            if label == "first":
                await asyncio.wait_for(self.two_active.wait(), timeout=0.2)
            await asyncio.sleep(float(prompt.variables["delay"]))
            return Completion(
                text=label,
                model=prompt.model or "model",
                provider=self.id,
                usage=Usage(input_tokens=1, output_tokens=1),
            )
        finally:
            self.active -= 1


def _runtime(tmp_path):
    registry = Registry()
    provider = AsyncProbeProvider()
    registry.register("assay.providers", provider.id, provider)
    return Runtime(
        workspace=Workspace(root=tmp_path),
        registry=registry,
        default_model="async_probe/model",
    ), provider


@pytest.mark.asyncio
async def test_aevaluate_overlaps_with_hard_ceiling_and_preserves_order(tmp_path):
    runtime, provider = _runtime(tmp_path)
    report = await runtime.aevaluate(
        PromptFile.parse(ASYNC_EVAL), max_concurrency=2
    )

    assert report["passed"] is True
    assert [case["id"] for case in report["cases"]] == [
        "first", "second", "third", "fourth"
    ]
    assert [case["output"] for case in report["cases"]] == [
        "first", "second", "third", "fourth"
    ]
    assert provider.peak == 2
    assert report["execution"]["mode"] == "bounded_concurrent"
    assert report["execution"]["max_concurrency"] == 2
    assert report["execution"]["scheduled_cases"] == 4


@pytest.mark.asyncio
async def test_aevaluate_one_worker_is_explicitly_serial(tmp_path):
    runtime, provider = _runtime(tmp_path)
    # Remove the structural two-worker requirement for this case set.
    cases = [{"id": "only", "input": {"label": "only", "delay": 0},
              "assert": [{"type": "contains", "value": "only"}]}]
    report = await runtime.aevaluate(
        PromptFile.parse(ASYNC_EVAL), cases=cases, max_concurrency=1
    )

    assert report["passed"] is True
    assert provider.peak == 1
    assert report["execution"]["max_concurrency"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 33, True, 1.5])
async def test_aevaluate_rejects_unbounded_or_ambiguous_worker_counts(tmp_path, value):
    runtime, _ = _runtime(tmp_path)
    with pytest.raises(ValueError, match="max_concurrency"):
        await runtime.aevaluate(PromptFile.parse(ASYNC_EVAL), max_concurrency=value)


class LegacySyncProvider:
    id = "legacy_sync"
    contract_version = "1.0"

    def capabilities(self, model: str) -> frozenset[str]:
        return frozenset({"text"})

    def list_models(self):
        return []

    def complete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        time.sleep(0.04)
        return Completion(
            text="legacy",
            model=prompt.model or "model",
            provider=self.id,
            usage=Usage(input_tokens=1, output_tokens=1),
        )


@pytest.mark.asyncio
async def test_arun_keeps_contract_1_0_sync_provider_compatible_and_nonblocking(tmp_path):
    registry = Registry()
    registry.register("assay.providers", "legacy_sync", LegacySyncProvider())
    runtime = Runtime(
        workspace=Workspace(root=tmp_path), registry=registry,
        default_model="legacy_sync/model",
    )
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: async/legacy\n"
        "model: {primary: legacy_sync/model}\n---\nhello"
    )
    ticked = asyncio.Event()

    async def ticker():
        await asyncio.sleep(0.005)
        ticked.set()

    result, _ = await asyncio.gather(runtime.arun(prompt), ticker())
    assert ticked.is_set()
    assert result.text == "legacy"
    assert result.completion.provider == "legacy_sync"


@pytest.mark.asyncio
async def test_arun_preserves_async_fallback_and_guardrail_evidence(tmp_path):
    runtime, _ = _runtime(tmp_path)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: async/guarded\n"
        "model: {primary: missing/model, fallbacks: [echo/echo]}\n"
        "guardrails:\n  - {type: pii, stage: output, action: redact}\n"
        "---\nContact ada@example.com"
    )
    result = await runtime.arun(prompt)

    assert result.fallback_used == "echo/echo"
    assert "ada@example.com" not in result.text
    assert result.guardrail_events[0]["action"] == "redact"


class RateLimitedProvider:
    id = "rate_limited"
    contract_version = CONTRACT_VERSION

    def __init__(self, failures: int, retry_after: str = "0") -> None:
        self.failures = failures
        self.retry_after = retry_after
        self.calls = 0
        self.seen_params: list[dict] = []

    def capabilities(self, model: str) -> frozenset[str]:
        return frozenset({"text"})

    def list_models(self):
        return []

    def _attempt(self, prompt: RenderedPrompt) -> Completion:
        self.calls += 1
        self.seen_params.append(dict(prompt.params))
        if self.calls <= self.failures:
            raise RateLimitError(
                "slow down", provider=self.id, retry_after=self.retry_after
            )
        return Completion(
            text="recovered", model=prompt.model or "model", provider=self.id,
            usage=Usage(input_tokens=1, output_tokens=1), latency_ms=7,
        )

    def complete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        return self._attempt(prompt)

    async def acomplete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        return self._attempt(prompt)


def _rate_runtime(tmp_path, provider: RateLimitedProvider) -> Runtime:
    registry = Registry()
    registry.register("assay.providers", provider.id, provider)
    return Runtime(workspace=Workspace(root=tmp_path), registry=registry)


def _rate_prompt(**params) -> PromptFile:
    encoded = ", ".join(f"{key}: {value}" for key, value in params.items())
    return PromptFile.parse(
        "---\npromptfile: 1\nid: rate/retry\n"
        f"model: {{primary: rate_limited/model, params: {{{encoded}}}}}\n"
        "---\nhello"
    )


@pytest.mark.asyncio
async def test_arun_retries_only_explicit_rate_limits_and_records_wait_evidence(tmp_path):
    provider = RateLimitedProvider(failures=2)
    result = await _rate_runtime(tmp_path, provider).arun(_rate_prompt(
        rate_limit_retries=2, rate_limit_backoff_s=0, rate_limit_max_wait_s=0,
    ))

    assert result.text == "recovered"
    assert provider.calls == 3
    assert all("rate_limit_retries" not in params for params in provider.seen_params)
    assert result.completion.raw["rate_limit"] == {
        "retries": 2,
        "wait_ms": 0,
        "events": [
            {"provider": "rate_limited", "model": "model", "retry": 1,
             "wait_ms": 0, "source": "retry_after_seconds"},
            {"provider": "rate_limited", "model": "model", "retry": 2,
             "wait_ms": 0, "source": "retry_after_seconds"},
        ],
    }


def test_sync_run_has_the_same_bounded_rate_limit_contract(tmp_path):
    provider = RateLimitedProvider(failures=1)
    result = _rate_runtime(tmp_path, provider).run(_rate_prompt(
        rate_limit_retries=1, rate_limit_backoff_s=0, rate_limit_max_wait_s=0,
    ))

    assert provider.calls == 2
    assert result.completion.raw["rate_limit"]["retries"] == 1


def test_runtime_does_not_retry_generic_provider_failures(tmp_path):
    class GenericFlakyProvider(RateLimitedProvider):
        def _attempt(self, prompt: RenderedPrompt) -> Completion:
            self.calls += 1
            if self.calls == 1:
                raise ProviderError("ordinary provider failure")
            return super()._attempt(prompt)

    provider = GenericFlakyProvider(failures=0)
    with pytest.raises(ProviderError):
        _rate_runtime(tmp_path, provider).run(_rate_prompt(
            rate_limit_retries=2, rate_limit_backoff_s=0, rate_limit_max_wait_s=0,
        ))
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_retry_after_is_capped_by_total_wait_budget(tmp_path, monkeypatch):
    provider = RateLimitedProvider(failures=1, retry_after="10")
    sleeps = []

    async def capture_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(runtime_module.asyncio, "sleep", capture_sleep)
    result = await _rate_runtime(tmp_path, provider).arun(_rate_prompt(
        rate_limit_retries=1, rate_limit_backoff_s=0.5, rate_limit_max_wait_s=0.02,
    ))

    assert sleeps == [pytest.approx(0.02)]
    assert result.completion.raw["rate_limit"]["wait_ms"] == 20
    assert result.completion.latency_ms == 27


@pytest.mark.parametrize(
    "params",
    [
        {"rate_limit_retries": 6},
        {"rate_limit_retries": True},
        {"rate_limit_backoff_s": -1},
        {"rate_limit_max_wait_s": 61},
    ],
)
def test_rate_limit_policy_rejects_unbounded_or_ambiguous_values(tmp_path, params):
    provider = RateLimitedProvider(failures=0)
    with pytest.raises(ProviderError, match="model.params.rate_limit"):
        _rate_runtime(tmp_path, provider).run(_rate_prompt(**params))
    assert provider.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "payload", "expected"),
    [
        (
            OpenAIProvider(api_key="test"),
            {"model": "model", "choices": [{"message": {"content": "openai"},
                                               "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 2, "completion_tokens": 1}},
            "openai",
        ),
        (
            AnthropicProvider(api_key="test"),
            {"model": "model", "content": [{"type": "text", "text": "anthropic"}],
             "usage": {"input_tokens": 2, "output_tokens": 1}, "stop_reason": "end_turn"},
            "anthropic",
        ),
        (
            GoogleProvider(api_key="test"),
            {"candidates": [{"content": {"parts": [{"text": "google"}]},
                              "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1}},
            "google",
        ),
        (
            OllamaProvider(),
            {"message": {"content": "ollama"}, "prompt_eval_count": 2,
             "eval_count": 1, "done_reason": "stop"},
            "ollama",
        ),
    ],
)
async def test_every_builtin_network_provider_uses_native_async_path(
    provider, payload, expected, monkeypatch
):
    calls = []

    async def apost(path, body, headers):
        calls.append((path, body, headers))
        return payload

    def sync_path_would_be_a_bug(*args, **kwargs):
        raise AssertionError("acomplete called the synchronous HTTP path")

    monkeypatch.setattr(provider, "_apost", apost)
    monkeypatch.setattr(provider, "_post", sync_path_would_be_a_bug)
    result = await provider.acomplete(RenderedPrompt(
        messages=[Message(role="user", content="hello")], model="model"
    ))

    assert result.text == expected
    assert result.usage.total_tokens == 3
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_astream_yields_live_deltas_then_one_auditable_result(tmp_path):
    runtime = Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/echo\nmodel: {primary: echo/echo}\n"
        "---\nThis answer is deliberately longer than one echo stream chunk."
    )

    events = [event async for event in runtime.astream(prompt)]

    assert len(events) > 2
    assert all(event.type == "delta" for event in events[:-1])
    assert events[-1].type == "completed"
    assert "".join(event.delta for event in events[:-1]) == events[-1].result.text
    assert events[-1].result.streaming == {
        "mode": "native",
        "chunks_received": len(events),  # text chunks plus provider's metadata chunk
        "chunks_delivered": len(events) - 1,
        "partial_delivery": False,
    }


@pytest.mark.asyncio
async def test_astream_attaches_delivery_evidence_before_tracing(tmp_path, monkeypatch):
    runtime = Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/traced\nmodel: {primary: echo/echo}\n"
        "---\ntrace this stream"
    )
    traced = []
    monkeypatch.setattr(runtime, "_trace", lambda result: traced.append(dict(result.streaming)))

    events = [event async for event in runtime.astream(prompt)]

    assert events[-1].type == "completed"
    assert traced == [events[-1].result.streaming]
    assert traced[0]["mode"] == "native"


@pytest.mark.asyncio
async def test_astream_buffers_before_output_guardrails_and_never_leaks_raw_text(tmp_path):
    runtime = Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/guarded\nmodel: {primary: echo/echo}\n"
        "guardrails:\n  - {type: pii, stage: output, action: redact}\n"
        "---\nEmail ada@example.com with the result."
    )

    events = [event async for event in runtime.astream(prompt)]

    assert [event.type for event in events] == ["delta", "completed"]
    assert all(event.buffered for event in events)
    assert "ada@example.com" not in events[0].delta
    assert "[EMAIL]" in events[0].delta
    assert events[-1].result.streaming["mode"] == "buffered_guardrails"
    assert events[-1].result.streaming["chunks_received"] > 1
    assert events[-1].result.guardrail_events[0]["action"] == "redact"


class BrokenStreamProvider:
    id = "broken_stream"
    contract_version = CONTRACT_VERSION

    def __init__(self, *, partial: bool) -> None:
        self.partial = partial

    def capabilities(self, model: str) -> frozenset[str]:
        return frozenset({"text", "streaming"})

    def list_models(self):
        return []

    def complete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        raise RuntimeError("non-streaming path is unavailable")

    async def astream(self, prompt: RenderedPrompt, **kwargs):
        if self.partial:
            yield StreamChunk(text="already sent", model="model", provider=self.id)
        raise RuntimeError("stream disconnected")


class ManyChunksProvider:
    id = "many_chunks"
    contract_version = CONTRACT_VERSION

    def capabilities(self, model: str) -> frozenset[str]:
        return frozenset({"text", "streaming"})

    def list_models(self):
        return []

    def complete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        raise AssertionError("streaming test used complete")

    async def astream(self, prompt: RenderedPrompt, **kwargs):
        for text in ("aa", "bb", "cc"):
            yield StreamChunk(text=text, model="model", provider=self.id)


class OversizedToolArgumentsProvider(ManyChunksProvider):
    id = "oversized_tool_arguments"

    def capabilities(self, model: str) -> frozenset[str]:
        return frozenset({"text", "tools", "streaming"})

    async def astream(self, prompt: RenderedPrompt, **kwargs):
        yield StreamChunk(tool_calls=[{
            "index": 0, "id": "call-1", "name": "lookup", "arguments": "x" * 200,
        }])


@pytest.mark.asyncio
async def test_astream_enforces_total_output_limit_before_next_delta(
    tmp_path, monkeypatch
):
    registry = Registry()
    registry.register("assay.providers", "many_chunks", ManyChunksProvider())
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/bounded\n"
        "model: {primary: many_chunks/model}\n---\nhello"
    )
    monkeypatch.setattr(runtime_module, "MAX_STREAM_OUTPUT_BYTES", 3)
    delivered = []

    with pytest.raises(ProviderError) as raised:
        async for event in runtime.astream(prompt):
            delivered.append(event.delta)

    assert delivered == ["aa"]
    assert raised.value.context["partial_output_delivered"] is True
    assert raised.value.context["chunks_delivered"] == 1


@pytest.mark.asyncio
async def test_astream_counts_tool_arguments_against_chunk_limit(tmp_path, monkeypatch):
    registry = Registry()
    registry.register(
        "assay.providers", "oversized_tool_arguments", OversizedToolArgumentsProvider()
    )
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/bounded-tool\n"
        "model: {primary: oversized_tool_arguments/model}\n"
        "tools: [{name: lookup}]\n---\nhello"
    )
    monkeypatch.setattr(runtime_module, "MAX_STREAM_CHUNK_BYTES", 100)

    delivered = []
    with pytest.raises(ProviderError) as raised:
        async for event in runtime.astream(prompt):
            delivered.append(event)

    assert delivered == []
    assert raised.value.context["partial_output_delivered"] is False


@pytest.mark.asyncio
async def test_guarded_stream_limit_fails_before_any_output(tmp_path, monkeypatch):
    registry = Registry()
    registry.register("assay.providers", "many_chunks", ManyChunksProvider())
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/bounded-guarded\n"
        "model: {primary: many_chunks/model}\n"
        "guardrails: [{type: pii, stage: output, action: redact}]\n---\nhello"
    )
    monkeypatch.setattr(runtime_module, "MAX_STREAM_CHUNKS", 2)

    with pytest.raises(ProviderError) as raised:
        async for _ in runtime.astream(prompt):
            pytest.fail("a guarded oversized stream delivered content")

    assert raised.value.context["partial_output_delivered"] is False


@pytest.mark.asyncio
async def test_astream_falls_back_only_before_any_partial_output(tmp_path):
    registry = Registry()
    registry.register("assay.providers", "broken_stream", BrokenStreamProvider(partial=False))
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/fallback\n"
        "model: {primary: broken_stream/model, fallbacks: [echo/echo]}\n"
        "---\nfallback answer"
    )

    events = [event async for event in runtime.astream(prompt)]
    assert events[-1].result.fallback_used == "echo/echo"
    assert "fallback answer" in events[-1].result.text


@pytest.mark.asyncio
async def test_astream_refuses_fallback_after_partial_delivery(tmp_path):
    registry = Registry()
    registry.register("assay.providers", "broken_stream", BrokenStreamProvider(partial=True))
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/partial\n"
        "model: {primary: broken_stream/model, fallbacks: [echo/echo]}\n"
        "---\nshould not replace"
    )
    delivered = []

    with pytest.raises(ProviderError) as raised:
        async for event in runtime.astream(prompt):
            delivered.append(event.delta)

    assert delivered == ["already sent"]
    assert raised.value.context["partial_output_delivered"] is True
    assert raised.value.context["chunks_delivered"] == 1


@pytest.mark.asyncio
async def test_astream_labels_sync_only_provider_as_buffered(tmp_path):
    registry = Registry()
    registry.register("assay.providers", "legacy_sync", LegacySyncProvider())
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/legacy\n"
        "model: {primary: legacy_sync/model}\n---\nhello"
    )

    events = [event async for event in runtime.astream(prompt)]
    assert [event.type for event in events] == ["delta", "completed"]
    assert all(event.buffered for event in events)
    assert events[-1].result.streaming["mode"] == "buffered_provider"


@pytest.mark.asyncio
async def test_astream_rejects_sampled_selection_semantics(tmp_path):
    runtime = Runtime(workspace=Workspace(root=tmp_path))
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/unsupported\n"
        "model: {primary: echo/echo, params: {samples: 2}}\n---\nhello"
    )
    with pytest.raises(ProviderError):
        async for _ in runtime.astream(prompt):
            pass


@pytest.mark.asyncio
async def test_astream_delivers_and_records_tool_call_deltas(tmp_path):
    runtime = Runtime(workspace=Workspace(root=tmp_path))
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/tools\n"
        "model:\n  primary: echo/agent\n  provider_params:\n    echo:\n"
        "      script:\n        - tool: search\n          arguments: {query: benchmark}\n"
        "tools: [{name: search}]\n---\nFind it"
    )

    events = [event async for event in runtime.astream(prompt)]

    assert "tool_call_delta" in [event.type for event in events]
    tool_event = next(event for event in events if event.type == "tool_call_delta")
    assert tool_event.tool_call == {
        "index": 0,
        "id": "echo-0",
        "name": "search",
        "arguments": {"query": "benchmark"},
    }
    result = events[-1].result
    assert result is not None
    assert result.completion.tool_calls == [{
        "name": "search", "arguments": {"query": "benchmark"}, "id": "echo-0",
    }]
    assert result.to_dict()["tool_calls"] == result.completion.tool_calls


class FragmentedToolProvider:
    id = "fragmented_tool"
    contract_version = CONTRACT_VERSION

    def capabilities(self, model: str) -> frozenset[str]:
        return frozenset({"text", "tools", "streaming"})

    def list_models(self):
        return []

    def complete(self, prompt: RenderedPrompt, **kwargs):
        raise AssertionError("streaming test used complete")

    async def astream(self, prompt: RenderedPrompt, **kwargs):
        yield StreamChunk(tool_calls=[{
            "index": 0, "id": "call-1", "name": "search", "arguments": '{"query":',
        }])
        yield StreamChunk(tool_calls=[{"index": 0, "arguments": '"assay"}'}])
        yield StreamChunk(model=prompt.model or "model", provider=self.id,
                          finish_reason="tool_calls")


@pytest.mark.asyncio
async def test_astream_assembles_fragmented_arguments_by_stable_call_index(tmp_path):
    registry = Registry()
    registry.register("assay.providers", "fragmented_tool", FragmentedToolProvider())
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/fragmented-tool\n"
        "model: {primary: fragmented_tool/model}\ntools: [{name: search}]\n---\nFind it"
    )

    events = [event async for event in runtime.astream(prompt)]

    assert [event.type for event in events] == [
        "tool_call_delta", "tool_call_delta", "completed",
    ]
    assert events[-1].result.completion.tool_calls == [{
        "name": "search", "arguments": {"query": "assay"}, "id": "call-1",
    }]


@pytest.mark.asyncio
async def test_astream_fails_closed_on_invalid_fragmented_arguments(tmp_path):
    class BrokenArgumentsProvider(FragmentedToolProvider):
        id = "broken_arguments"

        async def astream(self, prompt: RenderedPrompt, **kwargs):
            yield StreamChunk(tool_calls=[{
                "index": 0, "id": "call-1", "name": "search", "arguments": '{"query":',
            }])

    registry = Registry()
    registry.register("assay.providers", "broken_arguments", BrokenArgumentsProvider())
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry)
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: stream/broken-tool\n"
        "model: {primary: broken_arguments/model}\ntools: [{name: search}]\n---\nFind it"
    )

    with pytest.raises(ProviderError) as raised:
        async for _ in runtime.astream(prompt):
            pass
    assert raised.value.context["partial_output_delivered"] is True


@pytest.mark.asyncio
async def test_openai_stream_parser_preserves_deltas_and_final_usage(monkeypatch):
    provider = OpenAIProvider(api_key="test")

    async def events(*args, **kwargs):
        yield {"model": "model", "choices": [{"delta": {"content": "hel"},
                                                  "finish_reason": None}]}
        yield {"model": "model", "choices": [{"delta": {"content": "lo"},
                                                  "finish_reason": "stop"}]}
        yield {"model": "model", "choices": [],
               "usage": {"prompt_tokens": 3, "completion_tokens": 2}}

    monkeypatch.setattr(provider, "_astream_events", events)
    chunks = [chunk async for chunk in provider.astream(RenderedPrompt(
        messages=[Message(role="user", content="hi")], model="model"
    ))]

    assert "".join(chunk.text for chunk in chunks) == "hello"
    assert chunks[-1].usage.total_tokens == 5
    assert chunks[-1].cost_usd == 0.0  # unknown model is honestly unpriced


@pytest.mark.asyncio
async def test_openai_stream_parser_preserves_fragmented_tool_calls(monkeypatch):
    provider = OpenAIProvider(api_key="test")

    async def events(*args, **kwargs):
        yield {"model": "model", "choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call-1", "type": "function",
            "function": {"name": "search", "arguments": '{"query":'},
        }]}, "finish_reason": None}]}
        yield {"model": "model", "choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": '"assay"}'},
        }]}, "finish_reason": "tool_calls"}]}

    monkeypatch.setattr(provider, "_astream_events", events)
    chunks = [chunk async for chunk in provider.astream(RenderedPrompt(
        messages=[Message(role="user", content="hi")], model="model",
        tools=[{"name": "search"}],
    ))]

    assert [chunk.tool_calls[0]["index"] for chunk in chunks] == [0, 0]
    completion = runtime_module._merge_stream_tool_calls(chunks)
    assert completion == [{
        "name": "search", "arguments": {"query": "assay"}, "id": "call-1",
    }]


@pytest.mark.asyncio
async def test_anthropic_stream_parser_preserves_tool_input_json(monkeypatch):
    provider = AnthropicProvider(api_key="test")

    async def events(*args, **kwargs):
        yield {"type": "message_start", "message": {"model": "model", "usage": {}}}
        yield {"type": "content_block_start", "index": 2, "content_block": {
            "type": "tool_use", "id": "tool-2", "name": "lookup", "input": {},
        }}
        yield {"type": "content_block_delta", "index": 2,
               "delta": {"type": "input_json_delta", "partial_json": '{"id":7}'}}
        yield {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
               "usage": {"output_tokens": 4}}

    monkeypatch.setattr(provider, "_astream_events", events)
    chunks = [chunk async for chunk in provider.astream(RenderedPrompt(
        messages=[Message(role="user", content="hi")], model="model",
        tools=[{"name": "lookup"}],
    ))]

    assert runtime_module._merge_stream_tool_calls(chunks) == [{
        "name": "lookup", "arguments": {"id": 7}, "id": "tool-2",
    }]
    assert chunks[-1].usage.output_tokens == 4


def test_google_and_ollama_tool_payloads_are_not_silently_dropped():
    prompt = RenderedPrompt(
        messages=[Message(role="user", content="hi")],
        model="model",
        tools=[{
            "name": "lookup", "description": "Find one record",
            "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}},
        }],
    )

    google = GoogleProvider(api_key="test")._payload(prompt)
    declaration = google["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "lookup"
    assert declaration["parameters"] == prompt.tools[0]["input_schema"]

    observed = {}
    ollama = OllamaProvider()
    ollama._post = lambda path, body, headers: (
        observed.update(body=body) or {"message": {"content": ""}, "done_reason": "stop"}
    )
    ollama.complete(prompt)
    assert observed["body"]["tools"][0]["function"]["name"] == "lookup"


@pytest.mark.asyncio
async def test_google_stream_parser_preserves_complete_function_call(monkeypatch):
    provider = GoogleProvider(api_key="test")

    async def events(*args, **kwargs):
        yield {"candidates": [{"content": {"parts": [{"functionCall": {
            "name": "lookup", "args": {"id": 7}, "id": "google-1",
        }}]}, "finishReason": "STOP"}]}

    monkeypatch.setattr(provider, "_astream_events", events)
    chunks = [chunk async for chunk in provider.astream(RenderedPrompt(
        messages=[Message(role="user", content="hi")], model="model",
        tools=[{"name": "lookup"}],
    ))]

    assert runtime_module._merge_stream_tool_calls(chunks) == [{
        "name": "lookup", "arguments": {"id": 7}, "id": "google-1",
    }]


@pytest.mark.asyncio
async def test_ollama_stream_parser_preserves_complete_function_call(monkeypatch):
    provider = OllamaProvider()

    async def events(*args, **kwargs):
        yield {"message": {"content": "", "tool_calls": [{"function": {
            "name": "lookup", "arguments": {"id": 7},
        }}]}, "done": True, "done_reason": "stop", "eval_count": 2}

    monkeypatch.setattr(provider, "_astream_events", events)
    chunks = [chunk async for chunk in provider.astream(RenderedPrompt(
        messages=[Message(role="user", content="hi")], model="model",
        tools=[{"name": "lookup"}],
    ))]

    assert runtime_module._merge_stream_tool_calls(chunks) == [{
        "name": "lookup", "arguments": {"id": 7}, "id": None,
    }]


class _FakeStreamResponse:
    status_code = 200
    headers = {}

    def __init__(self, lines):
        self.lines = lines

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class _FakeStreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    def __init__(self, response, **kwargs):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, *args, **kwargs):
        return _FakeStreamContext(self.response)


@pytest.mark.asyncio
async def test_provider_stream_parser_rejects_oversized_raw_event_before_json(monkeypatch):
    response = _FakeStreamResponse(['data: {"metadata":"' + ("x" * 100) + '"}'])
    monkeypatch.setattr(providers_module, "MAX_STREAM_EVENT_BYTES", 32)
    monkeypatch.setattr(
        providers_module.httpx, "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(response, **kwargs),
    )
    provider = OpenAIProvider(api_key="test", base_url="https://example.invalid")

    with pytest.raises(ProviderError) as raised:
        async for _ in provider._astream_events("/stream", {}, {}, sse=True):
            pass

    assert raised.value.context["limit"] == "event_bytes"
    assert raised.value.context["event_bytes"] > 32


@pytest.mark.asyncio
async def test_provider_stream_parser_bounds_ignored_event_lines(monkeypatch):
    response = _FakeStreamResponse(["event: ping", "event: ping", "event: ping"])
    monkeypatch.setattr(providers_module, "MAX_STREAM_EVENTS", 2)
    monkeypatch.setattr(
        providers_module.httpx, "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(response, **kwargs),
    )
    provider = OpenAIProvider(api_key="test", base_url="https://example.invalid")

    with pytest.raises(ProviderError) as raised:
        async for _ in provider._astream_events("/stream", {}, {}, sse=True):
            pass

    assert raised.value.context == {
        "provider": "openai", "limit": "event_lines", "event_lines": 3,
    }

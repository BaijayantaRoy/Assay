"""OpenTelemetry spans carry useful evidence without leaking content by default."""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from assay_core.builtins.tracers import OpenTelemetryTracer
from assay_core.contracts import Completion, Message, RenderedPrompt, Usage


def _capture():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return OpenTelemetryTracer(provider), exporter


def _run(tracer: OpenTelemetryTracer):
    prompt = RenderedPrompt(
        messages=[Message(role="user", content="private customer text")],
        model="openai/gpt-test",
        params={"temperature": 0.2},
    )
    completion = Completion(
        text="private model output",
        model="gpt-test",
        provider="openai",
        usage=Usage(
            input_tokens=12, output_tokens=7, cached_input_tokens=3, reasoning_tokens=2
        ),
        latency_ms=125,
        cost_usd=0.004,
        finish_reason="stop",
    )
    tracer.on_run(
        prompt=prompt,
        completion=completion,
        meta={"run_id": "run-1", "prompt_id": "support/triage", "prompt_version": 4},
    )
    return completion


def test_genai_span_has_current_semantic_attributes_without_content(monkeypatch):
    monkeypatch.delenv("ASSAY_OTEL_LOG_CONTENT", raising=False)
    tracer, exporter = _capture()

    completion = _run(tracer)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat gpt-test"
    assert span.kind.name == "CLIENT"
    assert span.attributes["gen_ai.operation.name"] == "chat"
    assert span.attributes["gen_ai.provider.name"] == "openai"
    assert span.attributes["gen_ai.request.model"] == "gpt-test"
    assert span.attributes["gen_ai.usage.input_tokens"] == 12
    assert span.attributes["gen_ai.usage.output_tokens"] == 7
    assert span.attributes["gen_ai.usage.cache_read.input_tokens"] == 3
    assert span.attributes["gen_ai.usage.reasoning.output_tokens"] == 2
    assert span.attributes["assay.prompt.id"] == "support/triage"
    assert span.events == ()
    assert "private customer text" not in repr(span.attributes)
    assert "private model output" not in repr(span.attributes)
    assert completion.trace_id and len(completion.trace_id) == 32


def test_content_capture_is_explicit_and_uses_events(monkeypatch):
    monkeypatch.setenv("ASSAY_OTEL_LOG_CONTENT", "true")
    tracer, exporter = _capture()

    _run(tracer)

    events = exporter.get_finished_spans()[0].events
    assert [event.name for event in events] == [
        "gen_ai.input.messages", "gen_ai.output.messages"
    ]
    assert "private customer text" in events[0].attributes["gen_ai.input.messages"]
    assert "private model output" in events[1].attributes["gen_ai.output.messages"]

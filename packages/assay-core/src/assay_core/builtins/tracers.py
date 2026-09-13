"""OpenTelemetry observability with privacy-safe defaults.

The tracer follows the current OpenTelemetry GenAI semantic-convention names. Prompt
and completion content are excluded unless ``ASSAY_OTEL_LOG_CONTENT=true``; when enabled,
content is attached to span events rather than searchable span attributes.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from assay_core import __version__
from assay_core.contracts import CONTRACT_VERSION, Completion, RenderedPrompt


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _provider_name(provider: str) -> str:
    # OTel uses gcp.gen_ai for the Google GenAI API. Unknown/custom providers remain
    # valid strings and must not be guessed into a different vendor identity.
    return {"google": "gcp.gen_ai"}.get(provider, provider)


class OpenTelemetryTracer:
    """Emit one GenAI client span for each completed model call.

    Assay depends only on the OTel API. Applications configure their preferred SDK and
    exporter in the normal OpenTelemetry way; the ``assay-core[otel]`` extra supplies the
    SDK and OTLP/HTTP exporter for deployments that do not already have them.
    """

    id = "opentelemetry"
    contract_version = CONTRACT_VERSION

    def __init__(self, tracer_provider: Any = None) -> None:
        from opentelemetry import trace

        self._trace = trace
        self._tracer = trace.get_tracer(
            "assay_core.runtime", __version__, tracer_provider=tracer_provider
        )

    def on_run(
        self, *, prompt: RenderedPrompt, completion: Completion, meta: dict
    ) -> None:
        operation = "chat"
        model = completion.model or prompt.model or "unknown"
        attributes: dict[str, Any] = {
            "gen_ai.operation.name": operation,
            "gen_ai.provider.name": _provider_name(completion.provider),
            "gen_ai.request.model": model,
            "gen_ai.response.model": model,
            "gen_ai.output.type": "json" if prompt.output_schema else "text",
            "gen_ai.usage.input_tokens": completion.usage.input_tokens,
            "gen_ai.usage.output_tokens": completion.usage.output_tokens,
            "assay.run.id": str(meta.get("run_id", "")),
            "assay.prompt.id": str(meta.get("prompt_id", "")),
            "assay.prompt.version": int(meta.get("prompt_version", 1)),
            "assay.cost.usd": float(completion.cost_usd),
        }
        if completion.usage.cached_input_tokens:
            attributes["gen_ai.usage.cache_read.input_tokens"] = (
                completion.usage.cached_input_tokens
            )
        if completion.usage.reasoning_tokens:
            attributes["gen_ai.usage.reasoning.output_tokens"] = (
                completion.usage.reasoning_tokens
            )
        if completion.finish_reason:
            attributes["gen_ai.response.finish_reasons"] = [completion.finish_reason]
        streaming = meta.get("streaming") or {}
        if streaming:
            attributes["assay.streaming.mode"] = str(streaming.get("mode", "unknown"))
            attributes["assay.streaming.chunks_delivered"] = int(
                streaming.get("chunks_delivered", 0)
            )
            attributes["assay.streaming.partial_delivery"] = bool(
                streaming.get("partial_delivery", False)
            )
        temperature = prompt.params.get("temperature")
        if isinstance(temperature, (int, float)) and not isinstance(temperature, bool):
            attributes["gen_ai.request.temperature"] = float(temperature)

        end_time = time.time_ns()
        start_time = max(0, end_time - int(completion.latency_ms * 1_000_000))
        span = self._tracer.start_span(
            f"{operation} {model}",
            kind=self._trace.SpanKind.CLIENT,
            attributes=attributes,
            start_time=start_time,
        )
        try:
            if _enabled("ASSAY_OTEL_LOG_CONTENT"):
                span.add_event(
                    "gen_ai.input.messages",
                    {"gen_ai.input.messages": json.dumps(
                        [message.to_dict() for message in prompt.messages],
                        ensure_ascii=False,
                        default=str,
                    )},
                )
                span.add_event(
                    "gen_ai.output.messages",
                    {"gen_ai.output.messages": json.dumps(
                        [{"role": "assistant", "content": completion.text}],
                        ensure_ascii=False,
                    )},
                )
        finally:
            span.end(end_time=end_time)

        context = span.get_span_context()
        if context.is_valid:
            completion.trace_id = format(context.trace_id, "032x")

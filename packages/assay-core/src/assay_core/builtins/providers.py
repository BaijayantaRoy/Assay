"""Built-in providers (``assay.providers``).

Every provider is a thin HTTP client — no vendor SDKs — so the dependency surface
stays small and a new provider is one file plus one entry-point line.

Design notes
------------
* Portable ``params`` are mapped per provider; unmapped keys are dropped, never
  forwarded blindly, so a portable prompt cannot accidentally break on a new backend.
* ``provider_params[provider_id]`` is merged in last and passed through untouched.
  This is the escape hatch that keeps the format stable when a vendor ships a new knob.
* Pricing is resolved from the model catalogue (see ``assay_core.catalog``) rather than
  hardcoded, so cost tracking survives price changes without a code release.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, AsyncIterator, Iterable

import httpx

from ..catalog import ModelCatalog
from ..contracts import (
    CONTRACT_VERSION,
    Completion,
    ModelInfo,
    RenderedPrompt,
    StreamChunk,
    Usage,
)
from ..errors import AuthError, ProviderError, RateLimitError

DEFAULT_TIMEOUT = float(os.getenv("ASSAY_HTTP_TIMEOUT", "120"))
MAX_STREAM_EVENT_BYTES = 1024 * 1024
MAX_STREAM_EVENTS = 100_000


class _BaseProvider:
    id = "base"
    contract_version = CONTRACT_VERSION
    env_key: str = ""
    base_url: str = ""
    default_capabilities: frozenset[str] = frozenset({"text"})

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._catalog = ModelCatalog.default()

    # -- helpers -----------------------------------------------------------

    @property
    def api_key(self) -> str:
        key = self._api_key or (os.getenv(self.env_key) if self.env_key else None)
        if not key:
            raise AuthError(
                f"No API key for provider {self.id!r}. Set ${self.env_key}.",
                provider=self.id, env_var=self.env_key,
            )
        return key

    @property
    def url(self) -> str:
        return (self._base_url or os.getenv(f"ASSAY_{self.id.upper()}_BASE_URL") or self.base_url).rstrip("/")

    def capabilities(self, model: str) -> frozenset[str]:
        info = self._catalog.get(f"{self.id}/{model}")
        return info.capabilities if info and info.capabilities else self.default_capabilities

    def list_models(self) -> Iterable[ModelInfo]:
        return self._catalog.by_provider(self.id)

    def _cost(self, model: str, usage: Usage) -> float:
        info = self._catalog.get(f"{self.id}/{model}")
        if not info:
            return 0.0
        fresh = max(usage.input_tokens - usage.cached_input_tokens, 0)
        return round(
            fresh / 1e6 * info.input_cost_per_mtok
            + usage.cached_input_tokens / 1e6 * (info.cached_input_cost_per_mtok or info.input_cost_per_mtok)
            + usage.output_tokens / 1e6 * info.output_cost_per_mtok,
            8,
        )

    def _post(self, path: str, payload: dict, headers: dict) -> dict:
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                response = client.post(f"{self.url}{path}", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.id}: network error: {exc}", provider=self.id) from exc

        if response.status_code == 401:
            raise AuthError(f"{self.id}: unauthorized", provider=self.id)
        if response.status_code == 429:
            raise RateLimitError(
                f"{self.id}: rate limited",
                provider=self.id, retry_after=response.headers.get("retry-after"),
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"{self.id}: HTTP {response.status_code}: {response.text[:500]}",
                provider=self.id, status=response.status_code,
            )
        return response.json()

    async def _apost(self, path: str, payload: dict, headers: dict) -> dict:
        """Native async HTTP path used by ``Runtime.arun``."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.post(
                    f"{self.url}{path}", json=payload, headers=headers
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.id}: network error: {exc}", provider=self.id) from exc

        if response.status_code == 401:
            raise AuthError(f"{self.id}: unauthorized", provider=self.id)
        if response.status_code == 429:
            raise RateLimitError(
                f"{self.id}: rate limited",
                provider=self.id, retry_after=response.headers.get("retry-after"),
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"{self.id}: HTTP {response.status_code}: {response.text[:500]}",
                provider=self.id, status=response.status_code,
            )
        return response.json()

    async def _astream_events(
        self,
        path: str,
        payload: dict,
        headers: dict,
        *,
        sse: bool,
    ) -> AsyncIterator[dict]:
        """Yield bounded JSON events from SSE or JSONL provider responses."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                async with client.stream(
                    "POST", f"{self.url}{path}", json=payload, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        if response.status_code == 401:
                            raise AuthError(f"{self.id}: unauthorized", provider=self.id)
                        if response.status_code == 429:
                            raise RateLimitError(
                                f"{self.id}: rate limited",
                                provider=self.id,
                                retry_after=response.headers.get("retry-after"),
                            )
                        raise ProviderError(
                            f"{self.id}: HTTP {response.status_code}: {body[:500]}",
                            provider=self.id,
                            status=response.status_code,
                        )
                    event_lines = 0
                    async for raw_line in response.aiter_lines():
                        event_lines += 1
                        if event_lines > MAX_STREAM_EVENTS:
                            raise ProviderError(
                                f"{self.id}: stream exceeded {MAX_STREAM_EVENTS} event lines",
                                provider=self.id,
                                limit="event_lines",
                                event_lines=event_lines,
                            )
                        event_bytes = len(raw_line.encode("utf-8"))
                        if event_bytes > MAX_STREAM_EVENT_BYTES:
                            raise ProviderError(
                                f"{self.id}: streaming event exceeds "
                                f"{MAX_STREAM_EVENT_BYTES} bytes",
                                provider=self.id,
                                limit="event_bytes",
                                event_bytes=event_bytes,
                            )
                        line = raw_line.strip()
                        if not line or (sse and not line.startswith("data:")):
                            continue
                        if sse:
                            line = line.removeprefix("data:").strip()
                        if line == "[DONE]":
                            break
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ProviderError(
                                f"{self.id}: malformed streaming JSON",
                                provider=self.id,
                            ) from exc
                        if not isinstance(event, dict):
                            raise ProviderError(
                                f"{self.id}: streaming event must be an object",
                                provider=self.id,
                            )
                        yield event
        except (AuthError, RateLimitError, ProviderError):
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.id}: network error: {exc}", provider=self.id) from exc

    @staticmethod
    def _merge_extra(params: dict, prompt: RenderedPrompt, provider_id: str) -> dict:
        extra = (prompt.provider_params or {}).get(provider_id) or {}
        merged = dict(params)
        merged.update(extra)
        return merged

    def complete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:  # pragma: no cover
        raise NotImplementedError

    async def acomplete(
        self, prompt: RenderedPrompt, **kwargs: Any
    ) -> Completion:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# OpenAI / Chat Completions family
# ---------------------------------------------------------------------------


class OpenAIProvider(_BaseProvider):
    id = "openai"
    env_key = "OPENAI_API_KEY"
    base_url = "https://api.openai.com/v1"
    default_capabilities = frozenset({"text", "tools", "json_mode", "streaming", "vision"})
    _PARAM_MAP = {
        "temperature": "temperature", "top_p": "top_p", "max_tokens": "max_completion_tokens",
        "stop": "stop", "seed": "seed", "reasoning_effort": "reasoning_effort",
    }

    def _payload(self, prompt: RenderedPrompt) -> dict:
        payload: dict[str, Any] = {
            "model": prompt.model,
            "messages": [
                {"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})}
                for m in prompt.messages
            ],
        }
        for portable, native in self._PARAM_MAP.items():
            if portable in prompt.params:
                payload[native] = prompt.params[portable]
        if prompt.tools:
            payload["tools"] = [
                {"type": "function", "function": {
                    "name": t["name"], "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object"}),
                }}
                for t in prompt.tools
            ]
        if prompt.output_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": prompt.output_schema, "strict": True},
            }
        return self._merge_extra(payload, prompt, self.id)

    def complete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        data = self._post(
            "/chat/completions", self._payload(prompt),
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        return self._completion(prompt, data, int((time.perf_counter() - started) * 1000))

    async def acomplete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        data = await self._apost(
            "/chat/completions", self._payload(prompt),
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        return self._completion(prompt, data, int((time.perf_counter() - started) * 1000))

    def _completion(
        self, prompt: RenderedPrompt, data: dict, elapsed: int
    ) -> Completion:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        raw_usage = data.get("usage", {}) or {}
        usage = Usage(
            input_tokens=raw_usage.get("prompt_tokens", 0),
            output_tokens=raw_usage.get("completion_tokens", 0),
            cached_input_tokens=(raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            reasoning_tokens=(raw_usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
        )
        model = data.get("model", prompt.model or "")
        return Completion(
            text=message.get("content") or "",
            model=model, provider=self.id, usage=usage, latency_ms=elapsed,
            cost_usd=self._cost(model, usage),
            finish_reason=choice.get("finish_reason"),
            tool_calls=message.get("tool_calls") or [],
            raw=data,
        )

    async def astream(
        self, prompt: RenderedPrompt, **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        payload = self._payload(prompt)
        payload["stream"] = True
        options = dict(payload.get("stream_options") or {})
        options["include_usage"] = True
        payload["stream_options"] = options
        async for data in self._astream_events(
            "/chat/completions",
            payload,
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            sse=True,
        ):
            choices = data.get("choices") or []
            choice = choices[0] if choices else {}
            delta = choice.get("delta") or {}
            raw_usage = data.get("usage") or {}
            usage = None
            if raw_usage:
                usage = Usage(
                    input_tokens=raw_usage.get("prompt_tokens", 0),
                    output_tokens=raw_usage.get("completion_tokens", 0),
                    cached_input_tokens=(raw_usage.get("prompt_tokens_details") or {}).get(
                        "cached_tokens", 0
                    ),
                    reasoning_tokens=(raw_usage.get("completion_tokens_details") or {}).get(
                        "reasoning_tokens", 0
                    ),
                )
            model = data.get("model", prompt.model or "")
            text = delta.get("content") if isinstance(delta.get("content"), str) else ""
            tool_calls = delta.get("tool_calls") or []
            finish = choice.get("finish_reason")
            if text or tool_calls or usage is not None or finish:
                yield StreamChunk(
                    text=text,
                    model=model,
                    provider=self.id,
                    usage=usage,
                    cost_usd=self._cost(model, usage) if usage is not None else None,
                    finish_reason=finish,
                    tool_calls=tool_calls,
                    raw=data,
                )


class OpenAICompatibleProvider(OpenAIProvider):
    """Any OpenAI-shaped endpoint: vLLM, Together, Groq, Fireworks, OpenRouter, LM Studio.

    Configure with ``ASSAY_OPENAI_COMPATIBLE_BASE_URL`` and ``ASSAY_OPENAI_COMPATIBLE_API_KEY``,
    or per-workspace in ``assay.yaml``. This single class covers most of the long tail.
    """

    id = "openai_compatible"
    env_key = "ASSAY_OPENAI_COMPATIBLE_API_KEY"
    base_url = "http://localhost:8000/v1"


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class AnthropicProvider(_BaseProvider):
    id = "anthropic"
    env_key = "ANTHROPIC_API_KEY"
    base_url = "https://api.anthropic.com/v1"
    api_version = "2023-06-01"
    default_capabilities = frozenset(
        {"text", "tools", "vision", "streaming", "cache_control", "reasoning"}
    )
    _PARAM_MAP = {
        "temperature": "temperature", "top_p": "top_p",
        "max_tokens": "max_tokens", "stop": "stop_sequences",
    }

    def _payload(self, prompt: RenderedPrompt) -> dict:
        system_blocks: list[dict] = []
        turns: list[dict] = []
        for m in prompt.messages:
            if m.role in ("system", "developer"):
                block: dict[str, Any] = {"type": "text", "text": m.content}
                if m.cache:
                    block["cache_control"] = {"type": "ephemeral"}
                system_blocks.append(block)
            else:
                turns.append({"role": "assistant" if m.role == "assistant" else "user",
                              "content": m.content})

        payload: dict[str, Any] = {
            "model": prompt.model,
            "messages": turns or [{"role": "user", "content": prompt.text}],
            "max_tokens": prompt.params.get("max_tokens", 4096),
        }
        if system_blocks:
            payload["system"] = system_blocks
        for portable, native in self._PARAM_MAP.items():
            if portable in prompt.params and native != "max_tokens":
                payload[native] = prompt.params[portable]
        if prompt.tools:
            payload["tools"] = [
                {"name": t["name"], "description": t.get("description", ""),
                 "input_schema": t.get("input_schema", {"type": "object"})}
                for t in prompt.tools
            ]
        return self._merge_extra(payload, prompt, self.id)

    def complete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        data = self._post(
            "/messages", self._payload(prompt),
            {"x-api-key": self.api_key, "anthropic-version": self.api_version,
             "Content-Type": "application/json"},
        )
        return self._completion(prompt, data, int((time.perf_counter() - started) * 1000))

    async def acomplete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        data = await self._apost(
            "/messages", self._payload(prompt),
            {"x-api-key": self.api_key, "anthropic-version": self.api_version,
             "Content-Type": "application/json"},
        )
        return self._completion(prompt, data, int((time.perf_counter() - started) * 1000))

    def _completion(
        self, prompt: RenderedPrompt, data: dict, elapsed: int
    ) -> Completion:
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        tool_calls = [b for b in data.get("content", []) if b.get("type") == "tool_use"]
        raw_usage = data.get("usage", {}) or {}
        usage = Usage(
            input_tokens=raw_usage.get("input_tokens", 0),
            output_tokens=raw_usage.get("output_tokens", 0),
            cached_input_tokens=raw_usage.get("cache_read_input_tokens", 0),
        )
        model = data.get("model", prompt.model or "")
        return Completion(
            text=text, model=model, provider=self.id, usage=usage, latency_ms=elapsed,
            cost_usd=self._cost(model, usage), finish_reason=data.get("stop_reason"),
            tool_calls=tool_calls, raw=data,
        )

    async def astream(
        self, prompt: RenderedPrompt, **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        payload = self._payload(prompt)
        payload["stream"] = True
        input_tokens = 0
        cached_tokens = 0
        model = prompt.model or ""
        tool_blocks: dict[int, dict[str, Any]] = {}
        async for data in self._astream_events(
            "/messages",
            payload,
            {"x-api-key": self.api_key, "anthropic-version": self.api_version,
             "Content-Type": "application/json"},
            sse=True,
        ):
            event_type = data.get("type")
            if event_type == "message_start":
                message = data.get("message") or {}
                model = message.get("model", model)
                raw_usage = message.get("usage") or {}
                input_tokens = raw_usage.get("input_tokens", 0)
                cached_tokens = raw_usage.get("cache_read_input_tokens", 0)
                continue
            if event_type == "content_block_start":
                index = data.get("index", 0)
                block = data.get("content_block") or {}
                if block.get("type") == "tool_use":
                    tool_blocks[index] = {
                        "index": index,
                        "id": block.get("id"),
                        "name": block.get("name", ""),
                    }
                    initial = block.get("input")
                    yield StreamChunk(
                        model=model,
                        provider=self.id,
                        tool_calls=[{**tool_blocks[index], "arguments": initial or ""}],
                        raw=data,
                    )
                continue
            if event_type == "content_block_delta":
                delta = data.get("delta") or {}
                text = delta.get("text") if delta.get("type") == "text_delta" else ""
                if text:
                    yield StreamChunk(text=text, model=model, provider=self.id, raw=data)
                elif delta.get("type") == "input_json_delta":
                    index = data.get("index", 0)
                    call = tool_blocks.get(index, {"index": index})
                    yield StreamChunk(
                        model=model,
                        provider=self.id,
                        tool_calls=[{
                            **call,
                            "arguments": delta.get("partial_json", ""),
                        }],
                        raw=data,
                    )
                continue
            if event_type == "message_delta":
                raw_usage = data.get("usage") or {}
                usage = Usage(
                    input_tokens=input_tokens,
                    output_tokens=raw_usage.get("output_tokens", 0),
                    cached_input_tokens=cached_tokens,
                )
                yield StreamChunk(
                    model=model,
                    provider=self.id,
                    usage=usage,
                    cost_usd=self._cost(model, usage),
                    finish_reason=(data.get("delta") or {}).get("stop_reason"),
                    raw=data,
                )


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


class GoogleProvider(_BaseProvider):
    id = "google"
    env_key = "GOOGLE_API_KEY"
    base_url = "https://generativelanguage.googleapis.com/v1beta"
    default_capabilities = frozenset({"text", "tools", "vision", "json_mode", "streaming"})

    def _payload(self, prompt: RenderedPrompt) -> dict:
        contents, system = [], []
        for m in prompt.messages:
            if m.role in ("system", "developer"):
                system.append({"text": m.content})
            else:
                contents.append({
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                })
        gen: dict[str, Any] = {}
        if "temperature" in prompt.params:
            gen["temperature"] = prompt.params["temperature"]
        if "top_p" in prompt.params:
            gen["topP"] = prompt.params["top_p"]
        if "max_tokens" in prompt.params:
            gen["maxOutputTokens"] = prompt.params["max_tokens"]
        if "stop" in prompt.params:
            gen["stopSequences"] = prompt.params["stop"]
        if prompt.output_schema:
            gen["responseMimeType"] = "application/json"
            gen["responseSchema"] = prompt.output_schema

        payload: dict[str, Any] = {"contents": contents or [{"role": "user", "parts": [{"text": prompt.text}]}]}
        if system:
            payload["systemInstruction"] = {"parts": system}
        if gen:
            payload["generationConfig"] = gen
        if prompt.tools:
            payload["tools"] = [{"functionDeclarations": [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object"}),
                }
                for tool in prompt.tools
            ]}]
        return self._merge_extra(payload, prompt, self.id)

    def complete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        model = prompt.model or ""
        data = self._post(
            f"/models/{model}:generateContent?key={self.api_key}",
            self._payload(prompt), {"Content-Type": "application/json"},
        )
        return self._completion(prompt, data, int((time.perf_counter() - started) * 1000))

    async def acomplete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        model = prompt.model or ""
        data = await self._apost(
            f"/models/{model}:generateContent?key={self.api_key}",
            self._payload(prompt), {"Content-Type": "application/json"},
        )
        return self._completion(prompt, data, int((time.perf_counter() - started) * 1000))

    def _completion(
        self, prompt: RenderedPrompt, data: dict, elapsed: int
    ) -> Completion:
        model = prompt.model or ""
        candidates = data.get("candidates") or [{}]
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        tool_calls = [
            {
                "name": part["functionCall"].get("name", ""),
                "arguments": part["functionCall"].get("args") or {},
                "id": part["functionCall"].get("id"),
            }
            for part in parts if isinstance(part.get("functionCall"), dict)
        ]
        meta = data.get("usageMetadata", {}) or {}
        usage = Usage(
            input_tokens=meta.get("promptTokenCount", 0),
            output_tokens=meta.get("candidatesTokenCount", 0),
            cached_input_tokens=meta.get("cachedContentTokenCount", 0),
        )
        return Completion(
            text=text, model=model, provider=self.id, usage=usage, latency_ms=elapsed,
            cost_usd=self._cost(model, usage),
            finish_reason=candidates[0].get("finishReason"), tool_calls=tool_calls, raw=data,
        )

    async def astream(
        self, prompt: RenderedPrompt, **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        model = prompt.model or ""
        async for data in self._astream_events(
            f"/models/{model}:streamGenerateContent?alt=sse&key={self.api_key}",
            self._payload(prompt), {"Content-Type": "application/json"}, sse=True,
        ):
            candidates = data.get("candidates") or []
            candidate = candidates[0] if candidates else {}
            parts = (candidate.get("content") or {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts)
            tool_calls = [
                {
                    "index": index,
                    "name": part["functionCall"].get("name", ""),
                    "arguments": part["functionCall"].get("args") or {},
                    "id": part["functionCall"].get("id"),
                }
                for index, part in enumerate(parts)
                if isinstance(part.get("functionCall"), dict)
            ]
            raw_usage = data.get("usageMetadata") or {}
            usage = None
            if raw_usage:
                usage = Usage(
                    input_tokens=raw_usage.get("promptTokenCount", 0),
                    output_tokens=raw_usage.get("candidatesTokenCount", 0),
                    cached_input_tokens=raw_usage.get("cachedContentTokenCount", 0),
                )
            finish = candidate.get("finishReason")
            if text or tool_calls or usage is not None or finish:
                yield StreamChunk(
                    text=text,
                    model=model,
                    provider=self.id,
                    usage=usage,
                    cost_usd=self._cost(model, usage) if usage is not None else None,
                    finish_reason=finish,
                    tool_calls=tool_calls,
                    raw=data,
                )


# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------


class OllamaProvider(_BaseProvider):
    """Local models. No API key; zero cost; fully offline."""

    id = "ollama"
    env_key = ""
    base_url = "http://localhost:11434"
    default_capabilities = frozenset({"text", "streaming", "tools"})

    @property
    def api_key(self) -> str:
        return ""

    def list_models(self) -> Iterable[ModelInfo]:
        try:
            with httpx.Client(timeout=5) as client:
                data = client.get(f"{self.url}/api/tags").json()
        except Exception:
            return []
        return [
            ModelInfo(id=m["name"], provider=self.id, display_name=m["name"],
                      capabilities=self.default_capabilities)
            for m in data.get("models", [])
        ]

    def complete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        options = {}
        if "temperature" in prompt.params:
            options["temperature"] = prompt.params["temperature"]
        if "top_p" in prompt.params:
            options["top_p"] = prompt.params["top_p"]
        if "max_tokens" in prompt.params:
            options["num_predict"] = prompt.params["max_tokens"]
        payload = self._merge_extra(
            {
                "model": prompt.model,
                "messages": [{"role": m.role, "content": m.content} for m in prompt.messages],
                "stream": False,
                **({"tools": [{"type": "function", "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object"}),
                }} for tool in prompt.tools]} if prompt.tools else {}),
                **({"options": options} if options else {}),
            },
            prompt, self.id,
        )
        data = self._post("/api/chat", payload, {"Content-Type": "application/json"})
        return self._completion(prompt, data, int((time.perf_counter() - started) * 1000))

    async def acomplete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        options = {}
        if "temperature" in prompt.params:
            options["temperature"] = prompt.params["temperature"]
        if "top_p" in prompt.params:
            options["top_p"] = prompt.params["top_p"]
        if "max_tokens" in prompt.params:
            options["num_predict"] = prompt.params["max_tokens"]
        payload = self._merge_extra(
            {
                "model": prompt.model,
                "messages": [{"role": m.role, "content": m.content} for m in prompt.messages],
                "stream": False,
                **({"tools": [{"type": "function", "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object"}),
                }} for tool in prompt.tools]} if prompt.tools else {}),
                **({"options": options} if options else {}),
            },
            prompt, self.id,
        )
        data = await self._apost("/api/chat", payload, {"Content-Type": "application/json"})
        return self._completion(prompt, data, int((time.perf_counter() - started) * 1000))

    def _completion(
        self, prompt: RenderedPrompt, data: dict, elapsed: int
    ) -> Completion:
        usage = Usage(
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )
        return Completion(
            text=(data.get("message") or {}).get("content", ""),
            model=prompt.model or "", provider=self.id, usage=usage,
            latency_ms=elapsed, cost_usd=0.0,
            finish_reason=data.get("done_reason"),
            tool_calls=(data.get("message") or {}).get("tool_calls") or [], raw=data,
        )

    async def astream(
        self, prompt: RenderedPrompt, **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        options = {}
        if "temperature" in prompt.params:
            options["temperature"] = prompt.params["temperature"]
        if "top_p" in prompt.params:
            options["top_p"] = prompt.params["top_p"]
        if "max_tokens" in prompt.params:
            options["num_predict"] = prompt.params["max_tokens"]
        payload = self._merge_extra(
            {
                "model": prompt.model,
                "messages": [{"role": m.role, "content": m.content} for m in prompt.messages],
                **({"tools": [{"type": "function", "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object"}),
                }} for tool in prompt.tools]} if prompt.tools else {}),
                **({"options": options} if options else {}),
            },
            prompt, self.id,
        )
        payload["stream"] = True
        async for data in self._astream_events(
            "/api/chat", payload, {"Content-Type": "application/json"}, sse=False
        ):
            done = bool(data.get("done"))
            usage = None
            if done:
                usage = Usage(
                    input_tokens=data.get("prompt_eval_count", 0),
                    output_tokens=data.get("eval_count", 0),
                )
            yield StreamChunk(
                text=(data.get("message") or {}).get("content", ""),
                model=prompt.model or "",
                provider=self.id,
                usage=usage,
                cost_usd=0.0 if done else None,
                finish_reason=data.get("done_reason") if done else None,
                tool_calls=(data.get("message") or {}).get("tool_calls") or [],
                raw=data,
            )


class EchoProvider(_BaseProvider):
    """Deterministic offline provider. Powers tests, demos, and CI without API keys.

    Three models:

    ``echo/echo``
        Returns the rendered prompt.
    ``echo/json``
        Returns the render variables as JSON, so schema assertions work offline.
    ``echo/agent``
        Emits **scripted tool calls**, which is what makes agent harnesses and loops
        testable with no API key. Without this, the differentiating feature of this
        project would be the one part CI could not exercise.

    Scripting an agent run
    ----------------------
    A harness supplies a script through ``model.provider_params.echo.script``. Each
    entry is one turn::

        provider_params:
          echo:
            script:
              - { tool: fs.grep, arguments: { pattern: TODO } }
              - { tool: fs.read, arguments: { path: main.py } }
              - { text: "Found two TODOs in main.py." }

    Turns are consumed in order. The provider is stateless — it infers its position from
    how many ``[tool:…]`` observations are already in the message list, which keeps it
    correct under the stateless model the rest of the system uses.

    With no script, the fallback is: call the first available tool once, then answer.
    That gives a terminating two-iteration loop for any harness, so a newly written
    harness is runnable before anyone writes a script for it.
    """

    id = "echo"
    env_key = ""
    base_url = ""
    default_capabilities = frozenset({"text", "json_mode", "tools", "vision", "streaming"})

    @property
    def api_key(self) -> str:
        return ""

    def list_models(self) -> Iterable[ModelInfo]:
        return [
            ModelInfo(id="echo", provider=self.id, display_name="Echo (offline)",
                      context_window=1_000_000, capabilities=self.default_capabilities),
            ModelInfo(id="json", provider=self.id, display_name="Echo JSON (offline)",
                      context_window=1_000_000, capabilities=self.default_capabilities),
            ModelInfo(id="agent", provider=self.id, display_name="Echo Agent (offline, scriptable)",
                      context_window=1_000_000, capabilities=self.default_capabilities),
        ]

    def complete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        started = time.perf_counter()
        model = prompt.model or "echo"
        tool_calls: list[dict] = []

        if model.endswith("agent") or (prompt.tools and model.endswith("echo") is False):
            text, tool_calls = self._agent_turn(prompt)
        elif model.endswith("json"):
            text = json.dumps(prompt.variables or {"echo": True}, ensure_ascii=False)
        else:
            text = prompt.text

        usage = Usage(input_tokens=max(1, len(prompt.text) // 4),
                      output_tokens=max(1, len(text) // 4))
        return Completion(
            text=text, model=model, provider=self.id, usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000), cost_usd=0.0,
            finish_reason="tool_use" if tool_calls else "stop",
            tool_calls=tool_calls, raw={"offline": True},
        )

    async def acomplete(self, prompt: RenderedPrompt, **kwargs: Any) -> Completion:
        # Echo is in-memory and deterministic; yielding once makes cancellation fair
        # without paying for a worker thread.
        await asyncio.sleep(0)
        return self.complete(prompt, **kwargs)

    async def astream(
        self, prompt: RenderedPrompt, **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        completion = self.complete(prompt, **kwargs)
        # Deterministic fixed-size chunks make buffering and ordering testable without
        # pretending an offline in-memory provider has network token timing.
        for offset in range(0, len(completion.text), 16):
            await asyncio.sleep(0)
            yield StreamChunk(
                text=completion.text[offset:offset + 16],
                model=completion.model,
                provider=self.id,
            )
        yield StreamChunk(
            model=completion.model,
            provider=self.id,
            usage=completion.usage,
            cost_usd=completion.cost_usd,
            finish_reason=completion.finish_reason,
            tool_calls=completion.tool_calls,
            raw=completion.raw,
        )

    # -- scripted agent behaviour -----------------------------------------

    def _agent_turn(self, prompt: RenderedPrompt) -> tuple[str, list[dict]]:
        script = ((prompt.provider_params or {}).get(self.id) or {}).get("script") or []
        turn = self._turn_index(prompt)

        if script:
            if turn >= len(script):
                return "Script exhausted; concluding.", []
            entry = script[turn] or {}
            if entry.get("tool"):
                return (
                    entry.get("text", "") or f"Calling {entry['tool']}.",
                    [{"name": entry["tool"], "arguments": entry.get("arguments") or {},
                      "id": f"echo-{turn}"}],
                )
            return entry.get("text", "Done."), []

        # Unscripted fallback: one tool call, then an answer. Always terminates.
        available = [t.get("name") for t in (prompt.tools or []) if t.get("name")]
        if available and turn == 0:
            return (
                f"Using {available[0]} to gather information.",
                [{"name": available[0], "arguments": {}, "id": "echo-0"}],
            )
        return f"[echo/agent] completed after {turn} tool turn(s).", []

    @staticmethod
    def _turn_index(prompt: RenderedPrompt) -> int:
        """Infer which turn this is from the observations already in the transcript."""
        return sum(
            1 for message in prompt.messages
            if isinstance(message.content, str) and message.content.startswith("[tool:")
        )

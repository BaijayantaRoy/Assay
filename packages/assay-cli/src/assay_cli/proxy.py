"""OpenAI-compatible HTTP adapter for executing PromptFiles.

The adapter deliberately implements a small, explicit subset of Chat Completions.  Its
job is to let existing OpenAI clients call a reviewed artifact by id, not to turn Assay
into an unaudited arbitrary-prompt relay.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import jsonschema
from assay_core import AssayError, Runtime, Workspace
from assay_core.errors import (
    CapabilityError,
    GuardrailViolation,
    NotFound,
    ProviderError,
    RenderError,
    SpecError,
    ValidationError,
)
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger("assay.proxy")

SUPPORTED_PARAMS = {
    "temperature",
    "top_p",
    "max_tokens",
    "max_completion_tokens",
    "stop",
    "seed",
}
SUPPORTED_FIELDS = {
    "model",
    "messages",
    "variables",
    "upstream_model",
    "stream",
    "tools",
    "tool_choice",
    "n",
    *SUPPORTED_PARAMS,
}
MAX_REQUEST_BYTES = 1_048_576


def _openai_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Serialize portable complete calls to Chat Completions' wire shape."""
    return [
        {
            "id": call.get("id") or f"call_{index}",
            "type": "function",
            "function": {
                "name": call.get("name", ""),
                "arguments": json.dumps(
                    call.get("arguments") or {}, ensure_ascii=False, separators=(",", ":")
                ),
            },
        }
        for index, call in enumerate(calls)
    ]


def _error(
    status: int,
    message: str,
    *,
    code: str,
    param: str | None = None,
    error_type: str = "invalid_request_error",
) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        },
    )


def _artifact_ref(model: Any) -> tuple[str, int | None]:
    if not isinstance(model, str) or not model.startswith("assay:"):
        raise _error(
            400,
            "model must be an Assay artifact reference such as 'assay:support/triage'",
            code="invalid_assay_model",
            param="model",
        )
    raw = model.removeprefix("assay:")
    if not raw:
        raise _error(400, "model artifact id is empty", code="invalid_assay_model", param="model")
    prompt_id, marker, version_text = raw.rpartition("@")
    if marker and version_text.isdigit():
        if int(version_text) < 1:
            raise _error(400, "artifact version must be positive", code="invalid_version", param="model")
        return prompt_id, int(version_text)
    return raw, None


def _message_text(message: Any) -> str:
    if not isinstance(message, dict) or message.get("role") != "user":
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") not in {"text", "input_text"}:
                raise _error(
                    400,
                    "only text message content is supported by the Assay proxy",
                    code="unsupported_message_content",
                    param="messages",
                )
            if not isinstance(part.get("text"), str):
                raise _error(400, "message text must be a string", code="invalid_messages", param="messages")
            parts.append(part["text"])
        return "".join(parts)
    raise _error(400, "message content must be text", code="invalid_messages", param="messages")


def _variables(body: dict[str, Any]) -> dict[str, Any]:
    supplied = body.get("variables", {})
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict):
        raise _error(400, "variables must be an object", code="invalid_variables", param="variables")
    variables = dict(supplied)
    messages = body.get("messages")
    if messages is not None and not isinstance(messages, list):
        raise _error(400, "messages must be an array", code="invalid_messages", param="messages")
    if messages:
        if "input" in variables:
            raise _error(
                400,
                "messages and variables.input cannot both supply the PromptFile input",
                code="conflicting_input",
                param="messages",
            )
        if len(messages) != 1 or not isinstance(messages[0], dict) or messages[0].get("role") != "user":
            raise _error(
                400,
                "the bounded proxy accepts exactly one user message; pass structured data in variables",
                code="unsupported_conversation",
                param="messages",
            )
        text = _message_text(messages[0])
        if text:
            variables["input"] = text
    return variables


def _params(body: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(body) - SUPPORTED_FIELDS)
    if unknown:
        raise _error(
            400,
            f"unsupported Chat Completions field(s): {', '.join(unknown)}",
            code="unsupported_option",
            param=unknown[0],
        )
    unsupported = []
    if body.get("tools") or body.get("tool_choice"):
        unsupported.append("tools")
    if body.get("n", 1) != 1:
        unsupported.append("n")
    if unsupported:
        names = ", ".join(sorted(set(unsupported)))
        raise _error(
            400,
            f"unsupported Chat Completions option(s): {names}",
            code="unsupported_option",
            param=unsupported[0],
        )
    params = {key: body[key] for key in SUPPORTED_PARAMS if key in body}
    if "max_completion_tokens" in params:
        if "max_tokens" in params and params["max_tokens"] != params["max_completion_tokens"]:
            raise _error(
                400,
                "max_tokens and max_completion_tokens disagree",
                code="conflicting_options",
                param="max_completion_tokens",
            )
        params["max_tokens"] = params.pop("max_completion_tokens")
    return params


def _validate_variables(schema: dict[str, Any] | None, variables: dict[str, Any]) -> None:
    if not schema:
        return
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(variables),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path)
        suffix = f" at {location}" if location else ""
        raise _error(
            400,
            f"variables do not satisfy the PromptFile input schema{suffix}: {first.message}",
            code="input_schema_validation_failed",
            param="variables",
        )


def _token_ok(configured: str | None, authorization: str | None) -> bool:
    if not configured:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(authorization.removeprefix("Bearer "), configured)


async def _read_json_bounded(request: Request) -> Any:
    """Read one JSON body without trusting Content-Length or buffering without a cap."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_bytes = int(declared)
            if declared_bytes < 0:
                raise ValueError
            if declared_bytes > MAX_REQUEST_BYTES:
                raise _error(
                    413,
                    "request body exceeds the 1 MiB proxy limit",
                    code="request_too_large",
                )
        except ValueError as exc:
            raise _error(400, "invalid Content-Length header", code="invalid_content_length") from exc

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_REQUEST_BYTES:
            raise _error(
                413,
                "request body exceeds the 1 MiB proxy limit",
                code="request_too_large",
            )
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _error(400, "request body must be valid UTF-8 JSON", code="invalid_json") from exc


def create_proxy_app(
    *,
    workspace: str | Path | Workspace | None = None,
    token: str | None = None,
) -> FastAPI:
    """Create the proxy app. Passing a workspace/token makes tests deterministic."""
    if isinstance(workspace, Workspace):
        ws = workspace
    else:
        ws = Workspace.find(workspace or os.getenv("ASSAY_WORKSPACE"))
    runtime = Runtime(workspace=ws)
    store = ws.store()
    configured_token = (token if token is not None else os.getenv("ASSAY_PROXY_TOKEN")) or None

    app = FastAPI(
        title="Assay PromptFile Proxy",
        version="1.0.0",
        description=(
            "A bounded OpenAI Chat Completions adapter. Select a PromptFile with "
            "model=assay:<id>; guarded SSE streaming is supported; client-supplied "
            "tools are not."
        ),
    )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        detail = exc.detail
        if not isinstance(detail, dict) or "type" not in detail:
            detail = {
                "message": str(detail),
                "type": "invalid_request_error",
                "param": None,
                "code": "http_error",
            }
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(AssayError)
    async def assay_error(_request: Request, exc: AssayError):
        if isinstance(exc, NotFound):
            status, message, error_type = 404, exc.message, "invalid_request_error"
        elif isinstance(exc, ProviderError):
            status, message, error_type = 502, "upstream model request failed", "api_error"
            logger.warning("proxy upstream failure: %s", exc.code)
        elif isinstance(exc, (SpecError, ValidationError, RenderError)):
            status, message, error_type = 400, exc.message, "invalid_request_error"
        elif isinstance(exc, (CapabilityError, GuardrailViolation)):
            status, message, error_type = 422, exc.message, "invalid_request_error"
        else:
            status, message, error_type = 400, exc.message, "invalid_request_error"
        return JSONResponse(
            status_code=status,
            content={"error": {"message": message, "type": error_type, "param": None, "code": exc.code}},
        )

    async def authorize(authorization: str | None) -> None:
        if not _token_ok(configured_token, authorization):
            raise _error(
                401,
                "invalid or missing bearer token",
                code="invalid_api_key",
                error_type="authentication_error",
            )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "assay-promptfile-proxy",
            "authentication_required": bool(configured_token),
        }

    @app.get("/v1/models")
    async def models(authorization: str | None = Header(default=None)):
        await authorize(authorization)
        data = []
        for prompt_id in store.list():
            prompt = store.get(prompt_id)
            if prompt.kind != "prompt":
                continue
            data.append({
                "id": f"assay:{prompt.id}",
                "object": "model",
                "created": 0,
                "owned_by": "assay",
                "assay": {"prompt_id": prompt.id, "version": prompt.version, "status": prompt.status},
            })
        return {"object": "list", "data": data}

    @app.get("/v1/models/{model_id:path}")
    async def model(model_id: str, authorization: str | None = Header(default=None)):
        await authorize(authorization)
        prompt_id, version = _artifact_ref(model_id)
        prompt = store.get(prompt_id, version=version)
        if prompt.kind != "prompt":
            raise _error(404, "artifact is not executable as a chat completion", code="model_not_found")
        return {
            "id": f"assay:{prompt.id}@{prompt.version}",
            "object": "model",
            "created": 0,
            "owned_by": "assay",
            "assay": {"prompt_id": prompt.id, "version": prompt.version, "status": prompt.status},
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        await authorize(authorization)
        body = await _read_json_bounded(request)
        if not isinstance(body, dict):
            raise _error(400, "request body must be an object", code="invalid_request")

        prompt_id, version = _artifact_ref(body.get("model"))
        prompt = store.get(prompt_id, version=version)
        if prompt.kind != "prompt":
            raise _error(
                400,
                "only kind: prompt artifacts can be used through Chat Completions",
                code="unsupported_artifact_kind",
                param="model",
            )
        variables = _variables(body)
        _validate_variables(prompt.input_schema, variables)
        params = _params(body)
        upstream_model = body.get("upstream_model")
        if upstream_model is not None and not isinstance(upstream_model, str):
            raise _error(400, "upstream_model must be a string", code="invalid_upstream_model", param="upstream_model")

        if body.get("stream") is True:
            created = int(time.time())
            stream_id = f"chatcmpl-{os.urandom(12).hex()}"

            def sse(payload: Any) -> bytes:
                if payload == "[DONE]":
                    return b"data: [DONE]\n\n"
                return (
                    "data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    + "\n\n"
                ).encode("utf-8")

            async def generate():
                yield sse({
                    "id": stream_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": f"assay:{prompt.id}@{prompt.version}",
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "finish_reason": None,
                    }],
                })
                try:
                    async for event in runtime.astream(
                        prompt,
                        variables,
                        model=upstream_model,
                        params=params or None,
                    ):
                        if event.type == "delta":
                            yield sse({
                                "id": stream_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": f"assay:{prompt.id}@{prompt.version}",
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": event.delta},
                                    "finish_reason": None,
                                }],
                            })
                            continue
                        if event.type == "tool_call_delta" and event.tool_call is not None:
                            call = event.tool_call
                            function: dict[str, Any] = {}
                            if call.get("name"):
                                function["name"] = call["name"]
                            arguments = call.get("arguments")
                            if arguments not in (None, ""):
                                function["arguments"] = (
                                    arguments if isinstance(arguments, str)
                                    else json.dumps(
                                        arguments, ensure_ascii=False, separators=(",", ":")
                                    )
                                )
                            delta_call: dict[str, Any] = {
                                "index": call["index"],
                                "type": "function",
                                "function": function,
                            }
                            if call.get("id"):
                                delta_call["id"] = call["id"]
                            yield sse({
                                "id": stream_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": f"assay:{prompt.id}@{prompt.version}",
                                "choices": [{
                                    "index": 0,
                                    "delta": {"tool_calls": [delta_call]},
                                    "finish_reason": None,
                                }],
                            })
                            continue
                        result = event.result
                        if result is None:
                            continue
                        usage = result.completion.usage
                        yield sse({
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": f"assay:{prompt.id}@{prompt.version}",
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": (
                                    "tool_calls" if result.completion.tool_calls
                                    else result.completion.finish_reason or "stop"
                                ),
                            }],
                            "usage": {
                                "prompt_tokens": usage.input_tokens,
                                "completion_tokens": usage.output_tokens,
                                "total_tokens": usage.total_tokens,
                            },
                            "assay": {
                                "prompt_id": prompt.id,
                                "prompt_version": prompt.version,
                                "run_id": result.run_id,
                                "upstream_model": result.completion.model,
                                "provider": result.completion.provider,
                                "cost_usd": result.cost_usd,
                                "latency_ms": result.completion.latency_ms,
                                "streaming": result.streaming,
                            },
                        })
                except AssayError as exc:
                    message = (
                        "upstream model request failed"
                        if isinstance(exc, ProviderError) else exc.message
                    )
                    yield sse({
                        "error": {
                            "message": message,
                            "type": "api_error",
                            "param": None,
                            "code": exc.code,
                        }
                    })
                yield sse("[DONE]")

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        result = await runtime.arun(
            prompt,
            variables,
            model=upstream_model,
            params=params or None,
        )
        usage = result.completion.usage
        message: dict[str, Any] = {"role": "assistant", "content": result.text}
        if result.completion.tool_calls:
            message["tool_calls"] = _openai_tool_calls(result.completion.tool_calls)
        return {
            "id": f"chatcmpl-{result.run_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": f"assay:{prompt.id}@{prompt.version}",
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": (
                    "tool_calls" if result.completion.tool_calls
                    else result.completion.finish_reason or "stop"
                ),
            }],
            "usage": {
                "prompt_tokens": usage.input_tokens,
                "completion_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            },
            "assay": {
                "prompt_id": prompt.id,
                "prompt_version": prompt.version,
                "run_id": result.run_id,
                "upstream_model": result.completion.model,
                "provider": result.completion.provider,
                "cost_usd": result.cost_usd,
                "latency_ms": result.completion.latency_ms,
                "environment": result.environment.to_dict() if result.environment else None,
            },
        }

    return app

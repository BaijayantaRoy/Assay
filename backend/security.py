"""Application-layer access policy for the HTTP API.

Assay PromptFiles can contain executable loop steps.  The local workbench may use
mutation and execution endpoints without credentials, but those endpoints must never
become remotely reachable merely because Uvicorn was bound to ``0.0.0.0``.

Remote mutation is therefore an explicit two-part opt-in:

* ``ASSAY_ALLOW_REMOTE_MUTATIONS=true``; and
* a non-empty ``ASSAY_API_TOKEN`` supplied as ``Authorization: Bearer ...``.

When a token is configured it is required for local mutations as well.  Read-only
requests remain available so health checks and documentation can operate normally.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})
DEFAULT_MAX_BODY_BYTES = 5 * 1024 * 1024


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _bearer_token(header: str | None) -> str | None:
    if not header:
        return None
    scheme, separator, value = header.partition(" ")
    if not separator or scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    status_code: int = 200
    code: str = ""
    message: str = ""


def mutation_access(*, method: str, client_host: str | None,
                    authorization: str | None) -> AccessDecision:
    """Return the mutation decision without depending on an HTTP server.

    Keeping this pure makes the security boundary easy to mutation-test: changing any
    of the local-only, explicit-opt-in, or token checks must turn a focused test red.
    """

    if method.upper() in SAFE_METHODS:
        return AccessDecision(True)

    configured_token = os.getenv("ASSAY_API_TOKEN", "")
    supplied_token = _bearer_token(authorization)
    if configured_token and (
        supplied_token is None or not hmac.compare_digest(supplied_token, configured_token)
    ):
        return AccessDecision(
            False,
            401,
            "assay.security.authentication_required",
            "A valid Bearer token is required for API mutations.",
        )

    is_local = (client_host or "").lower() in LOOPBACK_HOSTS
    if is_local:
        return AccessDecision(True)

    if not _enabled("ASSAY_ALLOW_REMOTE_MUTATIONS"):
        return AccessDecision(
            False,
            403,
            "assay.security.remote_mutation_disabled",
            "Remote mutation and execution are disabled. Use the local workbench, or "
            "explicitly configure authenticated remote access.",
        )

    if not configured_token:
        return AccessDecision(
            False,
            503,
            "assay.security.remote_auth_not_configured",
            "Remote mutation was enabled without ASSAY_API_TOKEN; refusing unsafe access.",
        )

    return AccessDecision(True)


class ApiAccessMiddleware(BaseHTTPMiddleware):
    """Enforce local-first mutation access and a bounded declared request size."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method.upper() not in SAFE_METHODS:
            try:
                maximum = int(os.getenv("ASSAY_MAX_REQUEST_BYTES", DEFAULT_MAX_BODY_BYTES))
            except ValueError:
                maximum = DEFAULT_MAX_BODY_BYTES
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    too_large = int(content_length) > maximum
                except ValueError:
                    too_large = True
                if too_large:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": {
                            "code": "assay.security.request_too_large",
                            "message": f"Request body exceeds the {maximum}-byte limit.",
                        }},
                    )

        decision = mutation_access(
            method=request.method,
            client_host=request.client.host if request.client else None,
            authorization=request.headers.get("authorization"),
        )
        if not decision.allowed:
            return JSONResponse(
                status_code=decision.status_code,
                content={"detail": {"code": decision.code, "message": decision.message}},
                headers={"WWW-Authenticate": "Bearer"} if decision.status_code == 401 else None,
            )
        return await call_next(request)

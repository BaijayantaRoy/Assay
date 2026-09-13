"""Public REST API v1.

This is the *stable* surface. Everything under ``/v1`` is covered by the
compatibility policy in ``docs/architecture/adr/0004-compatibility-policy.md``:

* Additive changes only within a major version.
* A field is deprecated for at least twelve months before removal, and the
  deprecation is advertised in the ``Deprecation`` and ``Sunset`` response headers.
* Breaking changes ship under ``/v2`` while ``/v1`` keeps working.

The v1 API is implemented directly on top of ``assay_core`` rather than on the legacy
database models, so the REST surface, the CLI, and the MCP server are three faces of
one engine and cannot drift apart.
"""

from .agents import router as agents_router
from .health import router as workspace_router
from .integrations import router as integrations_router
from .packs import router as packs_router
from .router import router

__all__ = ["router", "agents_router", "workspace_router", "packs_router", "integrations_router"]

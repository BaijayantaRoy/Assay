import os
import sys
import webbrowser
import threading
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

VERSION = "1.0.0"

from .api.v1 import (
    agents_router as v1_agents_router,
    router as v1_router,
    workspace_router as v1_workspace_router,
    packs_router as v1_packs_router,
    integrations_router as v1_integrations_router,
)
from .security import ApiAccessMiddleware

LEGACY_API_ENABLED = os.getenv("ASSAY_ENABLE_LEGACY_API", "").strip().lower() in {
    "1", "true", "yes", "on",
}


def run_migrations():
    import subprocess
    try:
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(__file__))
        alembic_ini = os.path.join(base_dir, "alembic.ini")
        if os.path.exists(alembic_ini):
            subprocess.run(["alembic", "-c", alembic_ini, "upgrade", "head"], check=True)
    except Exception as e:
        print("Warning: Auto-migration failed:", e)

def open_browser():
    webbrowser.open("http://127.0.0.1:8001")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize compatibility storage only when the legacy API was requested."""
    if LEGACY_API_ENABLED:
        from .database import create_db_and_tables

        create_db_and_tables()
        run_migrations()
    
    if getattr(sys, 'frozen', False):
        threading.Timer(1.5, open_browser).start()
    yield


app = FastAPI(
    title="Assay API",
    description=(
        "Open-source prompt engineering platform.\n\n"
        "**`/v1` is the stable public API** — build against it. It is implemented on "
        "`assay-core`, the same engine behind the `assay` CLI and the MCP server, so all "
        "three surfaces behave identically.\n\n"
        "Legacy unversioned 0.x routes are disabled by default. Operators who still "
        "need that compatibility surface must set `ASSAY_ENABLE_LEGACY_API=1`."
    ),
    version=VERSION,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "v1", "description": "Stable public API. Covered by the compatibility policy."},
        {"name": "v1 · agents", "description": "Harnesses, loops, memory, red-teaming, progressive disclosure and judge calibration."},
        {"name": "system", "description": "Health and metadata."},
    ],
)

# PromptFiles can execute tools and loop shell steps.  Keep all mutations local unless
# remote access has been explicitly enabled *and* protected with a Bearer token.
app.add_middleware(ApiAccessMiddleware)

# Enable CORS — allow all localhost ports in dev, configurable via CORS_ORIGINS in prod
_env_origins = os.getenv("CORS_ORIGINS", "")
if _env_origins:
    allowed_origins = [o.strip() for o in _env_origins.split(",")]
else:
    # Development default: allow any localhost/127.0.0.1 port
    allowed_origins = [
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health Check ---

@app.get("/health", tags=["system"])
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": VERSION,
        "legacy_api_enabled": LEGACY_API_ENABLED,
    }


@app.get("/", tags=["system"])
def read_root():
    """Root endpoint with API info."""
    return {
        "message": "Assay API is running",
        "version": VERSION,
        "docs": "/docs",
    }


# --- Register Routers ---
#
# /v1 is the stable, versioned public surface, implemented on assay-core. It is the
# only API third parties should build against.
#
app.include_router(v1_router)
app.include_router(v1_agents_router)
app.include_router(v1_workspace_router)
app.include_router(v1_packs_router)
app.include_router(v1_integrations_router)

if LEGACY_API_ENABLED:
    # Compatibility only. The current workbench is entirely file-backed on `/v1`.
    from .api.routers import organizations, projects, prompts, utilities
    from .api.routers.abtests import router as abtests_router
    from .api.routers.advanced import router as advanced_router
    from .api.routers.chains import router as chains_router
    from .api.routers.compare import router as compare_router
    from .api.routers.evaluations import eval_router, router as datasets_router
    from .api.routers.guardrails import router as guardrails_router
    from .api.routers.intelligence import router as intelligence_router
    from .api.routers.library import router as library_router
    from .api.routers.models import router as models_router

    app.include_router(prompts.router)
    app.include_router(projects.router)
    app.include_router(organizations.router)
    app.include_router(utilities.router)
    app.include_router(datasets_router)
    app.include_router(eval_router)
    app.include_router(intelligence_router)
    app.include_router(compare_router)
    app.include_router(abtests_router)
    app.include_router(guardrails_router)
    app.include_router(advanced_router)
    app.include_router(chains_router)
    app.include_router(models_router)
    app.include_router(library_router)

# --- Serve Static Frontend (for PyInstaller standalone) ---
if getattr(sys, 'frozen', False):
    static_dir = os.path.join(sys._MEIPASS, "frontend", "out")
else:
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "out")

if os.path.isdir(static_dir):
    app.mount("/_next", StaticFiles(directory=os.path.join(static_dir, "_next")), name="next")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # API requests bypass this
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
            raise HTTPException(status_code=404)
            
        path = os.path.join(static_dir, full_path)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        
        # Fallback to index.html for SPA routing
        index_path = os.path.join(static_dir, "index.html")
        if os.path.isfile(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
                
        return HTMLResponse("<h1>Frontend build not found</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)

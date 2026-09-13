# Deployment Guide: Assay

Assay is designed to be easily deployed either locally for individual use or on a server for team collaboration.

---

## Option 1: Local Quickstart (No Docker)

For individual engineers running Windows, macOS, or Linux directly.

### Prerequisites
* Python 3.10 or higher
* Node.js 18 or higher

### Steps
1. Clone the repository.
2. (Optional) Copy `.env.example` to `.env` and add API keys.
3. Run the launch script:
   * **Windows**: Double-click `start-assay.bat`
   * **macOS / Linux**: Run `./start-assay.sh`

The script provisions the Python virtual environment, installs the editable Assay packages
and npm dependencies, and boots the file-backed FastAPI backend (port 8001) and Next.js
frontend (port 3001). The deprecated SQLite compatibility API is not initialized unless
`ASSAY_ENABLE_LEGACY_API=1` is explicitly set.

---

## Option 2: Docker Compose (Recommended for Teams)

For staging, production, or local environments that prefer containerization.

### Prerequisites
* Docker
* Docker Compose (v2)

### Steps
1. Clone the repository.
2. Create a `.env` file at the root based on `.env.example`.
3. Build and start the containers:
   ```bash
   docker compose up -d --build --wait
   ```

### Architecture Details
* **Backend Container**: Runs Python 3.12 slim, exposed on port `8001`.
* **Frontend Container**: Runs a multi-stage Node 20 alpine build (standalone mode), exposed on port `3001`.
* **Readiness**: Compose waits for the backend's `/health` probe before starting the
  frontend, and both services publish container health checks. A running process is not
  treated as a ready service.
* **Volume**: A persistent Docker volume named `assay-data` is mounted to `/app/data`; the
  canonical PromptFile workspace lives at `/app/data/workspace`. If the deprecated API is
  explicitly enabled for a migration, its SQLite and Chroma state can use the same volume,
  but neither is required by `/v1`.

---

## Option 3: Manual Production Deployment

If you are deploying to separate managed services (e.g., Vercel for frontend, Render/Railway for backend).

### Backend
1. Set the environment variable `CORS_ORIGINS` to match your frontend URL (e.g., `https://assay.vercel.app`).
2. Set `ASSAY_WORKSPACE` to a persistent directory containing `assay.yaml` and
   `prompts/`. `DATABASE_URL` is needed only when temporarily enabling the deprecated
   0.x compatibility API.
3. Start the server using Uvicorn:
   ```bash
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
   ```

### Frontend
1. Set the server-only `ASSAY_BACKEND_URL` environment variable to the backend origin
   (for example, `https://api.assay.com`). The browser uses the same-origin
   `/api/assay` proxy; backend credentials are never compiled into client JavaScript.
2. Build the project:
   ```bash
   npm run build
   ```
3. Start the Next.js server:
   ```bash
   npm start
   ```

---

## Environment Variables

| Variable | Location | Description |
|:--|:--|:--|
| `ASSAY_BACKEND_URL` | Frontend server | Backend origin used by the same-origin `/api/assay` proxy. Compose uses `http://backend:8001`; it is never exposed to browser code. |
| `ASSAY_WORKSPACE` | Backend | Persistent PromptFile workspace. Compose uses `/app/data/workspace`. |
| `DATABASE_URL` | Backend | Legacy-only SQLAlchemy connection string. |
| `CHROMA_DATA_PATH` | Backend | Legacy-only vector index path. |
| `CORS_ORIGINS` | Backend | Comma-separated list of allowed origins. Defaults to `http://localhost:3001`. |
| `ASSAY_ENABLE_LEGACY_API` | Backend | Opt in to deprecated unversioned SQLite routes for migration. Off by default. |
| `ASSAY_API_TOKEN` | Both | Required by the Compose deployment for authenticated mutating API calls and its server-side frontend proxy. |
| `ASSAY_ALLOW_REMOTE_MUTATIONS` | Backend | Explicit server-side opt-in for authenticated non-loopback mutation and execution. Compose sets it to `true`. |
| `OPENAI_API_KEY` | Backend | Optional credential for OpenAI-bound PromptFile runs and evals. |
| `ANTHROPIC_API_KEY` | Backend | Optional credential for Anthropic-bound PromptFile runs and evals. |

## OpenTelemetry export

Assay emits one client span per completed model call using the OpenTelemetry GenAI
semantic conventions. Prompt and completion content are excluded by default.

Install the exporter extra, then start the process through OpenTelemetry's standard
auto-configuration wrapper:

```bash
pip install -e "packages/assay-core[otel]"
OTEL_SERVICE_NAME=assay \
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example/v1/traces \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
opentelemetry-instrument assay run support/refund-triage \
  -v customer_tier=standard -v message="Where is my refund?"
```

For the API server, put `opentelemetry-instrument` before the existing Uvicorn command.
Set `ASSAY_OTEL_LOG_CONTENT=true` only after reviewing the privacy impact; content is then
recorded as span events, not indexed span attributes.

`GET /v1/observability` reports local SDK/exporter readiness. It intentionally leaves
`export_verified` as `null`: an endpoint being configured does not prove that its collector
received a span. Verify delivery in the telemetry backend.

| Variable | Default | Meaning |
|:--|:--|:--|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | OTLP collector endpoint. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | SDK default | Transport selected by the OTel SDK. |
| `OTEL_SERVICE_NAME` | SDK default | Service name attached to exported telemetry. |
| `ASSAY_OTEL_LOG_CONTENT` | `false` | Opt in to prompt/completion span events. |

## Release integrity

Tag and manual release-integrity runs use
`.github/workflows/release-integrity.yml` to build all four Python distributions and the
TypeScript SDK package, produce an SPDX JSON SBOM, and write a SHA-256 manifest. GitHub's
OIDC-backed artifact-attestation actions then associate signed build provenance and the SBOM
with those files. Every third-party action in the repository is pinned to an immutable commit,
and CI rejects a future floating tag.

The workflow creates evidence; it does not publish to PyPI or npm. A checked-in workflow is
also not proof that a particular release was attested. Verify a completed release with the
GitHub CLI and the actual downloaded subject:

```bash
gh attestation verify assay_core-1.0.0-py3-none-any.whl --repo baijayanta/Assay
sha256sum --check SHA256SUMS
```

The 2026-08-09 local smoke proof built both images with Docker Desktop 4.75.0, started the
documented Compose topology, and received HTTP 200 from backend health, the containerized
frontend, the same-origin API proxy, and a new-workspace health response. That proves this
environment and worktree, not every target platform; the CI Docker job remains the clean,
portable builder gate.

# Changelog

All notable changes to this project will be documented in this file.
This project follows the compatibility policy in
[ADR-0004](architecture/adr/0004-compatibility-policy.md).

## [Unreleased]

### Added

- **Async provider contract 1.1** — optional `AsyncProvider.acomplete`, native async HTTP
  for every built-in network provider, and worker-thread compatibility for 1.0 plugins.
- **Bounded eval execution** — `Runtime.aevaluate` and `assay test --max-workers N`
  enforce a 1–32 active-case ceiling, preserve declaration-order evidence, and expose the
  actual bound and wall time through CLI, REST, MCP, and both SDKs.
- **Throughput evidence gate** — a reproducible three-repetition synthetic benchmark
  requires identical serial/concurrent evidence, exactly four peak calls, and concurrent
  median wall time no greater than 50% of serial. It makes no hosted-model or competitor
  claim.
- **Guarded text and tool-call streaming** — optional provider-neutral
  `StreamingProvider.astream`, native OpenAI, Anthropic, Google, Ollama and echo parsers,
  `Runtime.astream`, CLI JSONL/human output, both SDKs, REST SSE, and OpenAI-compatible proxy
  SSE. Fragmented arguments assemble by stable call index and must decode to JSON objects;
  output controls buffer before delivery, and partial-stream failures never splice a fallback.
- **Stream-backed harness trajectories** — `harness.stream_model_calls: true` consumes each
  provider turn through the streaming contract, assembles tool fragments before dispatch,
  retains delivery evidence per step, and evaluates the resulting path with the same trajectory
  assertions. Sampled candidate selection is rejected before the provider call in this mode.
- **Bounded, auditable streaming** — provider-neutral limits cap chunk size, chunk count and
  total UTF-8 output, including tool argument bytes. Delivery evidence is attached before
  tracing and sealed into configured audit logs; guarded oversized streams fail before any
  content is released.
- **Independent PromptFile TypeScript implementation** — `@assay/promptfile` parses,
  validates and serializes Markdown/YAML/JSON without calling Python or REST. Both readers run
  the same six-fixture corpus, reject duplicate YAML keys, refuse future major versions and
  preserve unknown fields semantically.
- **Adaptive red-team strategies** — deterministic `sequence` and `adaptive` stages react to
  observed tool calls, arguments and results. The separate 24-case strategy corpus includes
  18 adversarial cases across at least 15 risk families plus six benign controls; incomplete
  deliveries are withheld from success-rate denominators.
- **Expanded fail-closed red-team corpus** — the static local regression set now carries 52
  attacks across 26 adversarial categories plus 12 benign controls, including SSRF,
  cross-tenant access, destructive actions, financial fraud, consent bypass, and privilege
  escalation. Corpus loading rejects ambiguous targets, expectation types, severity labels,
  and metadata semantics with file-and-line evidence; this remains a regression gate, not a
  safety certificate.
- **Precision-biased high-risk detection** — imperative patterns recognize all 12 new-family
  attacks while their four paired benign controls remain clean. The real scripted
  `agents/researcher` run moved from 25.0% to 46.15% detection (84.6% relative), with 52/52
  usable attacks, 0 errors, 0% ASR, and 0% false positives across 12 benign controls. This
  measures local defences, not real-model susceptibility.
- **Bounded rate-limit adaptation** — sync and async runs retry only explicit rate-limit
  errors, respect numeric/date `Retry-After` within a configurable total wait ceiling, strip
  runtime-only policy keys before provider calls, and retain wait/retry evidence in latency
  and completion metadata.
- **Repository-scale performance gate** — a generated 1,000-artifact/20-namespace workload
  checks the complete id set, unknown metadata and rendered edge inputs while gating median
  indexing and load+render time at conservative cross-platform regression ceilings.
- **Thread-safe plugin discovery** — registry completion is published only after every plugin
  group and built-in fallback is visible. A deterministic two-worker regression test and
  mutation prevent concurrent HTTP requests from observing an empty partial inventory.
- **Cross-theme accessibility contracts** — keyboard skip navigation, explicit icon-control
  labels, reduced-motion behavior, persistent cold-start page headings, and serious/critical
  WCAG checks across light, dark, and eye-care modes. The checks found and fixed the light
  palette's low-contrast accents and a pre-hydration dark-theme flash.

## [1.0.0] - 2026-07-27 — Foundation

The project is re-architected around a published file format and a plugin-first engine.
The web workbench and its unversioned API continue to work unchanged.

### Added

- **PromptFile v1 specification** — `spec/promptfile-v1.md` plus a JSON Schema, published
  under CC BY 4.0. Prompts are now plain-text files with conformance rules that guarantee
  lossless round-tripping and forward compatibility.
- **`assay-core`** — the engine. Nine versioned plugin contracts (renderers, providers,
  evaluators, guardrails, stores, importers, exporters, tracers, optimizers), an
  entry-point registry, and a runtime that composes them: render → guard → execute →
  guard → trace. 3 renderers, 6 providers, 29 evaluators, 5 guardrails ship built in,
  registered through the same public mechanism third-party plugins use.
- **`assay` CLI** — init, new, ls, show, render, run, test, lint, diff, history, models,
  plugins, spec, mcp, serve. Stable exit codes (4 = eval failure) make it a CI gate.
- **`assay-mcp`** — MCP server exposing prompts, resources and nine tools. Speaks both the
  session-based revisions and the stateless `2026-07-28` revision. Standard library only.
- **`/v1` REST API** — the stable public surface, implemented on `assay-core` so the API,
  CLI and MCP server cannot drift apart.
- **SDKs** — Python (embedded or remote, one API) and TypeScript (zero dependencies).
- **Capability negotiation** — a prompt declares what it needs and the runtime refuses to
  run without it, rather than silently degrading.
- **Offline execution** — the `echo` provider makes the entire toolchain usable and
  testable with no API key and no network.
- **Governance docs** — architecture blueprint, seven ADRs, roadmap with an explicit
  known-limitations table.

### Changed

- Model metadata moved out of code and into a layered data catalogue refreshed by
  `assay models sync`.
- CI now covers Python 3.10–3.13, spec conformance, the CLI exit-code contract, MCP
  protocol support and a secret scan.

### Removed

- **The licensing layer.** `licensing.py`, the `/license` router, the `require_pro_license`
  dependency, `FREE_VS_PRO.md` and all key material are gone. Every feature is free.
  Rationale: [ADR-0007](architecture/adr/0007-fully-open-source.md).

### Fixed

- Unquoted ISO timestamps in frontmatter no longer fail schema validation.
- `FileStore` no longer loses index entries written into a previously empty workspace.
- `min_context_tokens` is now enforced when no `capabilities` are declared.
- Prompt discovery prunes ignored directories during the walk instead of after, so it no
  longer stalls on repositories containing `node_modules` or a virtualenv.

---

## [0.5.0-beta] - 2026-05-17 — Public Beta Release 🚀

### Added — Galaxy-Class LLMOps Features
- **Prompt Intelligence Engine**: Real-time prompt scoring with clarity, specificity, structure, and length analysis
- **Model DNA Profiling**: Personality traits, power techniques, and optimal patterns for every major LLM
- **Cross-Model Adaptation** (Pro): LLM-powered prompt reformatting between providers (GPT ↔ Claude ↔ Gemini)
- **Prompt Library**: 50+ curated production-ready prompt templates across 10 professional categories
- **Global Model Registry**: 50+ pre-loaded models from OpenAI, Anthropic, Google, DeepSeek, Meta, Mistral, Alibaba, Cohere, and more
- **Model Sync**: Auto-sync pricing and availability from OpenRouter API (`sync_models.py`)
- **A/B Testing Framework** (Pro): Create A/B tests between prompt variants with traffic splitting and statistical significance
- **Multi-Model Comparator** (Pro): Compare same prompt across multiple models side-by-side with cost/latency breakdown
- **Prompt Chains**: Multi-step prompt workflows with variable piping between steps
- **Guardrails**: Input/output validation plus a fail-closed tool-result injection boundary
- **Tool integrity**: `assay tools pin` records tool metadata fingerprints; `--check`
  detects changed, removed, and newly unpinned tools without writing
- **Context depth**: incremental source-labelled compaction and selective clearing of old
  tool bodies without deleting the surrounding reasoning
- **Optimization**: `assay optimize` reports before/after scores, uncertainty and total
  cost, and writes only a candidate with a usable measured improvement
- **Test-time compute**: bounded majority/verifier selection for prompts and agent turns,
  with privacy-safe sample evidence and explicit accuracy/cost operating points
- **Environment Pinning** (Pro): Pin prompt versions to development/staging/production environments
- **Golden Test Suites** (Pro): Regression test cases per prompt with automated detection

### Added — Commercialization Infrastructure
- **Cryptographic Offline Licensing**: RSA-2048 public/private key system — verify Pro licenses offline with zero internet dependency
- **License Router**: `/license/` API endpoints for checking and activating licenses
- **Premium Feature Locks**: `require_pro_license` FastAPI dependency blocks free users from Pro endpoints with `403`
- **Freemium Architecture**: Frontend `LicenseContext` + backend enforcement on both tiers

### Added — Forward/Backward Compatibility
- **Alembic Migrations**: Full database migration system — new `.exe` versions safely upgrade old databases
- **AppData Isolation**: Database moved from project root to OS-standard AppData path (Windows: `%APPDATA%`, Mac: `~/Library/Application Support`, Linux: `~/.local/share`)
- **Cross-Platform Support**: Database and license paths work correctly on Windows, macOS, and Linux
- **API Versioning**: Export format uses `assay/v2` with graceful degradation for unknown fields

### Added — Standalone Packaging
- **Build Pipeline**: `build_portable.bat` script to compile frontend + backend into a single portable `.exe` via PyInstaller
- **Static Frontend Serving**: FastAPI serves the compiled Next.js app via `StaticFiles` in standalone mode
- **Auto-Browser Launch**: Portable `.exe` automatically opens the user's browser on startup

### Added — Quality Assurance
- **Automated Test Suite**: 24 pytest integration tests covering all API endpoints, licensing, and premium locks
- **Separated Dev Dependencies**: `requirements-dev.txt` for test/dev tools — NOT shipped with the executable
- **Test Runner**: `run_tests.bat` for one-click test execution

### Added — Documentation
- **README.md**: Complete rewrite for GitHub beta release with architecture diagrams and full API reference
- **USER_GUIDE.md**: Comprehensive 15-section user guide covering every feature
- **FREE_VS_PRO.md**: Detailed feature comparison table with FAQ
- **CHANGELOG.md**: Full release history (this file)

### Fixed — Deep Audit (11 issues resolved)
- **Critical**: Missing `HTTPException` import in `main.py` — would crash the portable `.exe`
- **Critical**: Deprecated `.dict()` still used in `list_chains` — replaced with explicit dict construction
- **Critical**: `ChainStep` creation used nonexistent fields (`name`, `input_mapping`) — aligned with model schema
- **High**: `private_key.pem` committed to Git — removed from tracking, added to `.gitignore`
- **High**: Three different version numbers across endpoints — centralized into single `VERSION` constant
- **Medium**: Duplicate `httpx` entry + missing `python-jose` in requirements — cleaned up
- **Medium**: `pytest` bundled in production requirements — separated into `requirements-dev.txt`
- **Medium**: `.gitignore` missing PyInstaller artifacts — added `.spec`, `private_key.pem`
- **Medium**: `APPDATA` env var is Windows-only — added full cross-platform detection
- **Low**: Temporary `fix_pages.py` script left in project root — deleted
- **Low**: Orphaned `layout.tsx` files from reverted static export — cleaned up

### Changed
- **Version Consistency**: App version centralized as `VERSION = "0.5.0"` in `main.py`
- **Database Path**: Now stored in OS AppData instead of project root
- **Theme Options**: Added Eye-Friendly mode alongside White and Dark themes
- **Datetime Handling**: All `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` across entire codebase

---

## [0.2.0] - 2026-05-09

### Added — Phase 2: Power Features
- **Import/Export System**: Export prompts and entire projects as JSON; import from JSON files
- **Prompt Playground**: Fill in `{{variables}}` and run prompts with live response preview
- **Dashboard Statistics**: Real-time counts for projects, prompts, versions, and evaluations via `/stats` API
- **Starter Templates**: 5 production-quality prompt templates seeded on first run (Customer Support, Code Review, Content Summarizer, SQL Generator, Meeting Notes)
- **API Enhancements**: New endpoints — `/stats`, `/prompts/all`, `/prompts/{id}/export`, `/projects/{id}/export`, `/projects/{id}/import`, `/playground/run`

### Added — Phase 3: Community & Ecosystem
- **Docker Support**: `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml` for one-command deployment
- **CI/CD Pipeline**: GitHub Actions workflow (`.github/workflows/ci.yml`) running pytest, lint, build, and Docker checks
- **Test Suite**: 18 pytest tests with in-memory SQLite fixtures covering all API endpoints
- **`.dockerignore`**: Keeps Docker images lean

### Changed
- **Dashboard**: Now fetches real statistics from backend instead of hardcoded values
- **API Client**: Added `uploadFile()` and `downloadJSON()` helpers; configurable `NEXT_PUBLIC_API_URL`
- **README.md**: Updated with Docker quickstart, expanded API reference (22 endpoints), refreshed roadmap

---

## [0.1.1] - 2026-05-09

### Added — Phase 1: Premium UI Overhaul
- **Dark Mode**: Full dark/light theme with toggle button and localStorage persistence
- **Toast Notifications**: Replaced all `alert()` calls with animated toast system (success/error/info)
- **Skeleton Loaders**: Loading placeholder UI on all pages
- **Collapsible Sidebar**: Logo branding, active route highlighting, collapse/expand toggle
- **Prompt Editor Upgrades**: Commit message dialog, `Ctrl+S` keyboard shortcut, copy-to-clipboard, word/char count, fullscreen mode
- **Tag System**: Tag input on prompt creation, tag badges on listing cards
- **Search Filter**: Client-side prompt filtering on project detail page
- **Settings Page**: Theme toggle, API key placeholders, database info, about section
- **Datasets Page**: Professional "Coming Soon" layout with test suite and dataset cards

### Added — Phase 0: Foundation
- **Startup Scripts**: `start-assay.bat` (Windows) and `start-assay.sh` (macOS/Linux) for one-click launch
- **GitHub Skeleton**: `.gitignore`, `LICENSE` (MIT), `README.md`, `.env.example`, `CONTRIBUTING.md`, `CHANGELOG.md`
- **Python Packages**: Added missing `__init__.py` files for all backend modules

### Fixed
- **database.py**: Path resolution now uses `pathlib` relative to project root (was CWD-dependent)
- **main.py**: Router imports moved to top; CORS origins configurable via env var; added `/health` endpoint
- **models.py**: Replaced deprecated `datetime.utcnow` with `datetime.now(timezone.utc)`
- **vector_db.py**: ChromaDB path resolution fixed; configurable via `CHROMA_DATA_PATH` env var
- **evaluation.py**: Same datetime deprecation fix
- **requirements.txt**: Pinned minimum versions; removed unused `psycopg2-binary`; added `pydantic-settings`
- **All Prompts page**: Fixed broken page — now loads all prompts via new `/prompts/all` endpoint

---

## [0.1.0] - 2026-05-08

### Added — MVP
- FastAPI backend with SQLModel/SQLite database
- ChromaDB vector search for semantic prompt discovery
- Next.js 16 frontend with React 19 and shadcn/ui components
- Prompt CRUD with version history
- Organization and project management
- Evaluation engine (mock implementation)
- Copy/duplicate prompt functionality

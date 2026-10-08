# Contributing to Assay

Assay treats assurance claims as product behavior. A contribution is ready when the code,
artifact evidence, public contract, and documentation agree—not merely when a happy-path test
is green.

## Set up a checkout

Fork the repository on GitHub, then clone your fork:

```bash
git clone https://github.com/<your-username>/Assay.git
cd Assay
pip install -e packages/assay-core -e packages/assay-cli -e packages/assay-mcp
cd frontend && npm install && cd ..
```

Use `start-assay.bat fresh` on Windows or `./start-assay.sh fresh` on macOS/Linux to start
and health-check the workbench.

## Repository map

| Path | Responsibility |
|:--|:--|
| `packages/assay-core/` | PromptFile parser, runtime, evals, harnesses, loops, governance, and plugin contracts |
| `packages/assay-cli/` | CLI and bounded OpenAI-compatible proxy |
| `packages/assay-mcp/` | MCP stdio/HTTP adapter |
| `backend/api/v1/` | Stable file-backed REST surface |
| `backend/api/routers/` | Deprecated opt-in 0.x compatibility surface |
| `frontend/app/` | Next.js workbench over `/v1` |
| `spec/` | Published PromptFile v1 schema and red-team corpus |
| `packs/` | Installable PromptFiles; generated domain packs have a checked-in generator |
| `prompts/` | Artifacts used by Assay itself |
| `tests/e2e/` | Installed binaries, real sockets, MCP stdio, API/UI contracts, and proxy tests |
| `tests/mutation/` | Mutants that prove critical assertions can fail |
| `docs/architecture/adr/` | Accepted decisions and their tradeoffs |

Read `AGENTS.md` and the relevant ADR before a cross-cutting change.

## Non-negotiable invariants

1. Never report more than was measured. Zero usable samples means a rate is withheld.
2. `verified` is tri-state; `None` means nothing was checked.
3. A test must be able to fail for the behavior named in its assertion.
4. Unknown PromptFile fields must round-trip untouched.
5. The public format key is `promptfile:`, never the product name.

Changing a `/v1` response requires updating the real-server UI contract test. TypeScript types
do not validate runtime JSON.

## Development guidance

### Python and REST

- Keep business behavior in `assay-core`; CLI, MCP, and REST should remain adapters.
- Add type hints and concise docstrings to public APIs.
- Return structured error codes and preserve the distinction between invalid, denied,
  unavailable, failed, and not checked.
- Run the smallest relevant unit and real-boundary test while iterating.

Start the backend with:

```bash
python -m uvicorn backend.main:app --reload --port 8001
```

### Frontend

- Use `frontend/lib/v1.ts`, the only supported workbench API client.
- Keep secrets in server/process configuration. Browser code may show credential presence but
  must never accept, store, or return a provider key.
- Pair every metric with its denominator or unavailable reason.
- Verify responsive behavior; desktop-only layout is a release defect.

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

### PromptFiles and packs

- Reuse an existing artifact before creating a duplicate.
- Every new executable artifact needs at least one meaningful eval.
- A catalog render-contract check proves template wiring only; do not call it semantic quality.
- Regenerate curated packs with `python scripts/build_curated_packs.py`, and use `--check` to
  verify checked-in output.

## Required checks

Run these before opening a pull request:

```bash
pytest packages/assay-core/tests
pytest tests/e2e
assay lint && assay spec validate .
python tests/mutation/run_mutations.py --check
```

Run the full mutation campaign for engine or assertion changes:

```bash
python tests/mutation/run_mutations.py
```

Also run `pytest backend/tests`, the frontend checks above, and `mkdocs build --strict` when
their surfaces changed. Live provider behavior, Docker images, and browser rendering are not
proven by the offline Python suite; state those boundaries honestly in the pull request.

## Pull requests

Use a focused branch and a conventional commit subject. The PR should say:

- what user-visible behavior changed;
- which evidence proves it;
- which claims remain unverified;
- whether any response shape, spec field, security boundary, or compatibility promise changed;
- how to reproduce the result without secrets when possible.

Do not loosen an assertion simply to restore green. Fix the behavior or explain why the
assertion itself was invalid and demonstrate that the replacement catches a mutant.

## Reporting issues

Open a [GitHub issue](https://github.com/BaijayantaRoy/Assay/issues) with the smallest reproducer,
command and error code, expected and actual behavior, and Python/Node/OS versions. For a
security issue, use the repository's private security-reporting channel rather than publishing
an exploit in a public issue.

Contributions are licensed under the MIT License; the standalone specification is CC BY 4.0.

# Maintainers

| Area | Maintainer |
|:--|:--|
| Everything | [@BaijayantaRoy](https://github.com/BaijayantaRoy) |

One maintainer, stated honestly. See [GOVERNANCE.md](GOVERNANCE.md).

## Reviewing a pull request

What a reviewer checks, in order — and it is the same list whether the PR came from a
stranger or from the maintainer:

1. **Does a claim in this PR overstate what it measured?** This outranks correctness,
   because a wrong number that looks right is worse than a bug that announces itself.
2. **Can the new test fail?** If it is not obvious, break the code on purpose and confirm it
   goes red. Two tests in this repository once asserted orderings that held regardless of
   the values they claimed to test; mutation testing caught both.
3. **Did a public contract change?** Spec field, `/v1` response shape, plugin protocol,
   exit code, security boundary. If yes, it needs an ADR and a changelog entry, and
   `tests/e2e/test_ui_contract_e2e.py` pins the `/v1` field names the workbench reads.
4. **Is `verified` still tri-state everywhere it travels** — engine, API, and the colour the
   workbench paints?
5. **Does the PR say what it could not verify?** A PR that lists nothing unverified has
   usually not looked.

## Never

- Loosen an assertion to restore green. Fix the behaviour, or show the assertion was wrong
  and prove the replacement catches a mutant.
- Merge a new executable artifact with no eval case.
- Edit an accepted ADR to make a past decision look better. Supersede it.

## Releasing

1. `docs/CHANGELOG.md` — every public-contract change, each deprecation with its removal version
   named now.
2. Full check suite, including `pytest tests/benchmark` and
   `python tests/mutation/run_mutations.py` in full, not `--check`.
3. `assay lint && assay spec validate .`
4. `mkdocs build --strict`
5. Tag `vX.Y.Z`. The release workflow re-runs the suites at the tagged commit, builds
   and attests every artifact, and publishes the GitHub Release. Registry publishing
   (`assay-core`, `assay-cli`, `assay-mcp`, `assay-client`, `@assay/sdk`,
   `@assay/promptfile`) is a separate, manual step.
6. Scrub document metadata on anything released as a downloadable artifact.

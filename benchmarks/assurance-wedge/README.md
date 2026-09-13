# Portable assurance-as-code benchmark

This kit measures the narrow competitive wedge named in
[`docs/architecture/BENCHMARK.md`](../../docs/architecture/BENCHMARK.md). It is deliberately
incapable of turning Assay's component tests into a competitor result.

## Run it

```bash
python benchmarks/assurance-wedge/score.py
python benchmarks/assurance-wedge/score.py --check
python benchmarks/assurance-wedge/plan_trials.py --check
python benchmarks/assurance-wedge/export_operator_kit.py --check
pytest tests/benchmark/test_scorecard.py
```

The first command regenerates the canonical result and the portal's checked-in projection.
The second fails on drift. The current trial ledger is empty, so the correct result is a
withheld claim with zero competitive KPIs proven.

## Add evidence

1. Use the exact tasks and qualification rules in `protocol.json`.
2. Capture every run in `trials/current.json` using `trial.schema.json`.
3. Keep failed and unusable runs. For loss rates, unusable runs receive zero success credit;
   incomplete change tasks consume the full 45-minute timebox.
4. Put every raw artifact beneath the trial ledger directory and attach its relative URI and
   lowercase SHA-256 digest. The CLI scorer verifies containment, file presence, and content.
5. Use at least three trials and two distinct operators for every product/metric result,
   and cover every task declared for that metric. The four-fault reporting metric therefore
   needs at least four trials per product; repeating one easy fault cannot qualify.
6. Run the scorer and review the generated result before committing it.

The neutral fixtures under `fixtures/` are the inputs every product receives. Do not translate
or simplify a fixture before the stopwatch begins. Record a completed trial with
`record_trial.py`; it requires explicit usable/completed flags, copies the raw evidence beneath
the ledger, verifies content digests, validates the prospective full ledger, and rejects
duplicate IDs instead of overwriting evidence.

`plans/full-target-template.json` is a generated 50-slot assignment template covering Assay and
all four named comparators. Its operator ids are roles, not people, and its records are never
counted as evidence. Regenerate it with `plan_trials.py`; replace roles with real identities only
when scheduling independent execution.

`export_operator_kit.py` produces the portal-downloadable deterministic ZIP. It includes the
protocol, schema, neutral fixtures, empty ledger, recorder, scorer, and full-target role plan,
plus an internal `SHA256SUMS`. The bundle is operator input, not trial evidence.

```bash
python benchmarks/assurance-wedge/record_trial.py \
  --id assay-faults-operator-a-001 \
  --product-id assay --product-version 1.0.0 \
  --metric-id false-assurance-miss-rate --task-id zero-usable-sample \
  --operator-id operator-a --task-author-id task-author \
  --os windows-11 --runtime python-3.12 --clean-setup \
  --usable --completed \
  --measurement delivered_faults=4 --measurement detected_faults=4 \
  --artifact path/to/raw-run.json
```

The scorer also refuses to call a 0% versus 0% tie “50% better.” A release claim requires all
three primary metrics, at least three comparators, and independently reproducible evidence.

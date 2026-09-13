# Curated PromptFile packs

This catalog ships **203 PromptFiles** across ten installable packs: the original starter
set plus product, writing, research, data, operations, customer, education, trust, and
engineering collections.

Every file is subject to the same executable gate:

- strict PromptFile v1 validation;
- globally unique artifact id;
- stable status and at least one embedded eval;
- offline execution through the deterministic `echo` provider;
- JSON Schema-valid eval inputs;
- every required input affects the rendered template; and
- deleting the template must make its eval fail.

The 180 files marked `x-assay-pack: curated-v1` declare
`x-assay-eval-scope: render-contract-only`. That wording is deliberate: their bundled
checks prove file integrity, input wiring, and the instructional contract. They do **not**
claim that every model will produce a semantically correct answer. After installing a
blueprint, bind the intended production model and add domain behavior cases before using
it as a release gate.

The curated files are generated deterministically from reviewed task definitions:

```bash
python scripts/build_curated_packs.py --check
pytest packages/assay-core/tests/test_packs.py
```

Run the generator without `--check` only after changing its catalog. Generated files are
ordinary PromptFiles and remain readable, diffable, installable, and forkable.

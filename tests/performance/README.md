# Performance evidence

Run the deterministic scheduler benchmark with:

```bash
python tests/performance/run_eval_throughput.py --check
python tests/performance/run_repository_scale.py --check
```

The gate compares Assay's serial evaluator with its bounded-concurrency evaluator on the
same 12-case, fixed-latency workload. It requires identical ordered evidence, exactly four
peak active calls, and a concurrent median no greater than 50% of the serial median. Raw
repetitions are printed as JSON.

This deliberately supports only a narrow claim about Assay's own scheduler. It is not a
hosted-model benchmark, a quality benchmark, or evidence that Assay is faster than another
product. Real-provider benchmarks must disclose the provider, model, region, rate limits,
dataset, warm-up policy, and all failed or unusable trials.

`run_repository_scale.py` builds 1,000 small PromptFiles across 20 namespaces in a temporary
directory. It gates real file-store indexing and load+render medians at conservative 5-second
ceilings while checking the complete id set, rendered edge inputs, and unknown metadata. File
creation is excluded; the result is a regression budget, not a filesystem leaderboard.

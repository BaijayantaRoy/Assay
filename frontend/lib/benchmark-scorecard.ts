import generatedResult from "@/lib/benchmark-result.generated.json";
import generatedPlan from "@/lib/benchmark-plan.generated.json";
import generatedOperatorKit from "@/lib/benchmark-operator-kit.generated.json";

export type BenchmarkState = "component_verified" | "not_measured";

export type BenchmarkMetric = {
  id: string;
  name: string;
  direction: "lower_is_better";
  unit: string;
  formula: string;
  releaseTarget: string;
  assayResult: string;
  comparatorResult: string;
  state: BenchmarkState;
  evidence: string[];
  nextRun: string;
};

export type BenchmarkResult = {
  claim_status: "verified" | "withheld";
  claim_verified: boolean;
  competitive_kpis_proven: number;
  evidence_date: string;
  primary_kpi_count: number;
  protocol_sha256: string;
  trials_sha256: string;
  minimum_comparators: number;
  qualifying_comparator_count: number;
  recorded_trial_count: number;
  minimum_qualifying_trial_records: number;
  minimum_record_gap: number;
};

export type BenchmarkPlan = {
  plan_kind: "role-template-not-evidence";
  product_ids: string[];
  planned_trial_records: number;
  claim_minimum_trial_records: number;
};

export type BenchmarkOperatorKit = {
  file: string;
  sha256: string;
  bytes: number;
  file_count: number;
  evidence_status: "operator-inputs-not-trial-evidence";
};

const result = generatedResult as BenchmarkResult;
const plan = generatedPlan as BenchmarkPlan;
const operatorKit = generatedOperatorKit as BenchmarkOperatorKit;

/**
 * Published claim ledger for the narrow assurance-as-code benchmark wedge.
 *
 * Component evidence is deliberately not promoted into a comparative result. The
 * `not_measured` comparator remains visible until a fair, reproducible run exists.
 */
export const BENCHMARK_SCORECARD = {
  snapshot: "10 Aug 2026 · release matrix verified",
  claim: result.claim_verified
    ? "50%-better competitive claim verified"
    : "50%-better competitive claim withheld",
  result,
  plan,
  operatorKit,
  wedge:
    "Portable assurance-as-code: executable artifacts, evals, controls, lifecycle state, and honest evidence semantics travel together.",
  primary: [
    {
      id: "false-assurance-miss-rate",
      name: "False-assurance miss rate",
      direction: "lower_is_better",
      unit: "seeded faults missed / seeded faults delivered",
      formula: "missed seeded reporting faults ÷ all delivered seeded reporting faults",
      releaseTarget:
        "0 misses, and a rate at least 50% lower than the best measured comparator",
      assayResult: "Component gate: 0 of 44 prior full-campaign mutants and 0 of 2 current contract mutants survived",
      comparatorResult: "Not measured on the shared task corpus",
      state: "component_verified",
      evidence: [
        "46/46 current anchors valid; prior 44/44 full campaign and 2/2 new security-contract mutants killed",
        "Tri-state verification preserved across core, API, SDK, and portal",
        "Zero-usable rates are withheld instead of displayed as reassuring zeroes",
      ],
      nextRun:
        "Deliver the same zero-sample, unchecked-handoff, missing-cost, and uncalibrated-judge faults to every product and retain unusable trials in the denominator.",
    },
    {
      id: "portable-evidence-loss-rate",
      name: "Portable-evidence loss rate",
      direction: "lower_is_better",
      unit: "required evidence fields lost / required evidence fields seeded",
      formula:
        "required fields missing after export, import, and offline review ÷ required fields seeded",
      releaseTarget:
        "0 lost fields, and a rate at least 50% lower than the best measured comparator",
      assayResult:
        "Component gate: Python and TypeScript conformance pass; generated unknown fields round-trip",
      comparatorResult: "Not measured on the shared portability fixture",
      state: "component_verified",
      evidence: [
        "Independent Python and TypeScript readers pass the shared valid/invalid fixtures",
        "100 generated unknown-value examples round-trip in Python",
        "PromptFile carries evals, controls, lifecycle, and extensions in one file",
      ],
      nextRun:
        "Seed identical eval, control, provenance, lifecycle, and unknown-extension fields, then score loss after each product's supported export/import path and offline review.",
    },
    {
      id: "auditable-change-effort",
      name: "Auditable-change effort",
      direction: "lower_is_better",
      unit: "median operator minutes",
      formula:
        "median elapsed minutes from clean clone to reviewed failing-then-passing eval",
      releaseTarget:
        "Median effort no greater than 50% of the best measured comparator",
      assayResult: "Not measured with independent operators",
      comparatorResult: "Not measured with independent operators",
      state: "not_measured",
      evidence: [
        "Offline echo provider removes credential and inference-cost prerequisites",
        "CLI, MCP, REST, SDK, and portal use the same file-backed engine",
        "Release artifacts and clean-machine commands are already documented",
      ],
      nextRun:
        "Use task-author/operator separation, clean environments, the same instructions, and raw screen/command logs; a second person must reproduce the ranking.",
    },
  ] satisfies BenchmarkMetric[],
  guardrails: [
    "Use the same seeded repository, operator instructions, stopwatch rule, and clean environment.",
    "Keep failures and unusable trials in the denominator; never convert not checked into passed.",
    "Record product versions, environment, raw artifacts, scoring code, and manual transformations.",
    "Require independent reproduction before publishing any 50%-better claim.",
    "State category limits: Promptfoo is broader in red teaming; hosted platforms are broader in production operations.",
  ],
  protocolAssets: [
    "Six neutral tasks: four reporting faults, one 14-field portability fixture, and one red-to-green change task",
    "Operator recorder with explicit usable/completed states, duplicate rejection, raw-evidence copying, and atomic ledger writes",
    "Content-level SHA-256 verification for every checked-in raw artifact",
    "Seventeen benchmark tests plus schema, generated-result, 50-slot plan, and operator-kit drift gates in CI",
    "Deterministic 15-file operator kit with an internal SHA-256 manifest and a portal-published archive digest",
  ],
  minimumEvidence: [
    `${result.minimum_qualifying_trial_records} qualifying trial records minimum across Assay plus any three comparators: four reporting-fault tasks and three trials for each remaining KPI per product`,
    "At least two distinct operators for every product/KPI result, with task-author/operator separation",
    "Every task declared for a metric must be covered; repeating one easy task cannot qualify a product",
    "Raw artifact SHA-256 digests, product versions, environments, elapsed time, and unusable trials retained",
  ],
};

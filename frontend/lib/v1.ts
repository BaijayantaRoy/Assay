/**
 * Typed client for the stable `/v1` surface.
 *
 * This is the workbench's only API client. It talks to the published file-backed
 * contract; the former `lib/api.ts` client for unversioned 0.x database routes was removed
 * when every live page migrated to `/v1`.
 *
 * Every type here was derived by calling the endpoint and reading the response, not by
 * reading the handler and assuming. Fields the UI does not use are still declared where
 * their absence would be surprising to the next reader.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "/api/assay";

export class V1Error extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "V1Error";
  }
}

/**
 * The engine returns structured errors: `{detail: {code, message}}`. Flattening them to
 * a bare string here would throw away the code, which is the part a caller can branch on
 * and the part worth showing a user who intends to file a bug.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/v1${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new V1Error(
      `Cannot reach the API at ${BASE}. Is the backend running?`,
      0,
      "assay.unreachable",
    );
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (detail && typeof detail === "object") {
      throw new V1Error(detail.message || res.statusText, res.status, detail.code);
    }
    throw new V1Error(
      typeof detail === "string" ? detail : res.statusText,
      res.status,
    );
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

/** Ids are path-like (`agents/researcher`) and go into the URL path, not a query. */
const idPath = (id: string) =>
  id.split("/").map(encodeURIComponent).join("/");

// ---------------------------------------------------------------------------
// harnesses
// ---------------------------------------------------------------------------

export type HarnessSummary = {
  id: string;
  name: string | null;
  version: number;
  status: string;
  tools: string[];
  max_iterations: number | null;
  stream_model_calls: boolean;
  budget: { cost_usd?: number; wallclock_s?: number; tool_calls?: number };
  memory: boolean;
  has_evals: boolean;
};

export type ToolResult = {
  tool: string;
  arguments: Record<string, unknown>;
  content: string;
  is_error: boolean;
  denied: boolean;
  denied_reason: string;
  latency_ms: number;
};

export type TrajectoryStep = {
  index: number;
  text: string;
  tool_calls: { name: string; arguments: Record<string, unknown>; id: string }[];
  tool_results: ToolResult[];
  context_tokens: number;
  context_action: string;
  cost_usd: number;
  latency_ms: number;
  streaming?: {
    mode: "native" | "buffered_provider";
    chunks_received: number;
    partial_delivery: boolean;
  };
};

export type Trajectory = {
  run_id: string;
  harness_id: string;
  harness_version: number;
  goal: string;
  /** `completed` | `budget_exceeded` | `max_iterations` | `failed` | `denied` */
  status: string;
  stop_reason: string;
  output: string;
  iterations: number;
  tool_calls: string[];
  tool_errors: number;
  denied_calls: string[];
  cost_usd: number;
  total_tokens: number;
  wallclock_s: number;
  model: string;
  budget: Record<string, number>;
  /** `null` when the harness declares no verification — not the same as `false`. */
  verified: boolean | null;
  verification_detail: string;
  steps: TrajectoryStep[];
};

export const listHarnesses = () => get<HarnessSummary[]>("/harnesses");

export const runHarness = (
  id: string,
  body: { goal?: string; variables?: Record<string, unknown>; dry_run?: boolean },
) => post<Trajectory>(`/harnesses/${idPath(id)}/run`, body);

export const evaluateHarness = (id: string) =>
  post<EvalReport>(`/harnesses/${idPath(id)}/evaluate`);

// ---------------------------------------------------------------------------
// loops
// ---------------------------------------------------------------------------

export type LoopSummary = {
  id: string;
  name: string | null;
  version: number;
  status: string;
  trigger: string;
  goal: string;
  max_cycles: number;
  steps: number;
  has_verification: boolean;
};

export type LoopStep = {
  id: string;
  type: string;
  command: string;
  output: string;
  exit_code: number | null;
  failed: boolean;
  wallclock_s: number;
  /** `null` means this step declared no check, so nothing was verified. */
  verified: boolean | null;
  verification_detail: string;
};

export type LoopCycle = {
  cycle: number;
  steps: LoopStep[];
  verified: boolean | null;
  verification_detail: string;
  goal_met: boolean;
  cost_usd: number;
  wallclock_s: number;
};

export type LoopRun = {
  run_id: string;
  loop_id: string;
  loop_version: number;
  goal: string;
  trigger: string;
  /** `goal_met` | `stalled` | `max_cycles` | `failed`. `stalled` ≠ `verification_failed`. */
  status: string;
  stop_reason: string;
  goal_met: boolean;
  cycles: LoopCycle[];
  cycle_count: number;
  cost_usd: number;
  wallclock_s: number;
  state: Record<string, unknown>;
};

export const listLoops = () => get<LoopSummary[]>("/loops");

export const runLoop = (
  id: string,
  body: { variables?: Record<string, unknown>; max_cycles?: number } = {},
) => post<LoopRun>(`/loops/${idPath(id)}/run`, body);

// ---------------------------------------------------------------------------
// memory
// ---------------------------------------------------------------------------

export type MemoryNamespace = {
  records: number;
  kinds: Record<string, number>;
  oldest: string | null;
  newest: string | null;
  path: string;
};

export type MemoryOverview = {
  namespaces: Record<string, MemoryNamespace>;
  total: number;
};

export type MemoryRecord = {
  id: string;
  kind: "episodic" | "semantic" | string;
  namespace: string;
  content: string;
  tags: string[];
  entities: string[];
  source_run_id: string | null;
  source_id: string | null;
  outcome: string | null;
  created_at: string;
  /** Hybrid recall score. Entity matches weigh heaviest; see `builtins/memory.py`. */
  score: number;
};

export const memoryOverview = () => get<MemoryOverview>("/memory");

/**
 * `namespace` defaults to `"default"` server-side, which is almost never what a caller
 * wants — records are written under the harness's own namespace. Callers should pass one
 * from `memoryOverview()`.
 */
export const searchMemory = (
  q: string,
  namespace: string,
  limit = 10,
  kind?: "episodic" | "semantic",
) =>
  get<{ query: string; namespace: string; count: number; results: MemoryRecord[] }>(
    `/memory/search?q=${encodeURIComponent(q)}` +
      `&namespace=${encodeURIComponent(namespace)}` +
      (kind ? `&kind=${kind}` : "") +
      `&limit=${limit}`,
  );

// ---------------------------------------------------------------------------
// red team
// ---------------------------------------------------------------------------

export type AttackResult = {
  id: string;
  category: string;
  severity: string;
  /** `defended` | `compromised` | `errored` */
  outcome: string;
  complied: boolean;
  compliance_reason: string;
  detected?: boolean;
  strategy: "static" | "sequence" | "adaptive";
  turns_planned: number;
  turns_delivered: number;
  delivery_complete: boolean;
  detail?: string;
  [k: string]: unknown;
};

type RedTeamReportBase = {
  harness_id: string;
  model: string;
  /** `scripted` means an offline provider: this measured defences, not susceptibility. */
  mode: string;
  mode_note: string;
  corpus: string;
  created_at: string;
  passed: boolean;
  /**
   * False when every attack errored. Without this a run where nothing executed reports
   * a 0% attack-success rate — the most dangerous number in the product.
   */
  errored: number;
  errors: string[];
  attacks_run: number;
  benign_controls: number;
  by_category: Record<
    string,
    { total: number; compromised: number; detected: number }
  >;
  by_strategy: Record<
    string,
    { selected: number; usable: number; compromised: number; errored: number }
  >;
  compromised: unknown[];
  results: AttackResult[];
};

export type RedTeamReport = RedTeamReportBase &
  (
    | {
        usable: false;
        attack_success_rate: null;
        detection_rate: null;
        false_positive_rate: number | null;
      }
    | {
        usable: true;
        attack_success_rate: number;
        detection_rate: number;
        /** Null when the selected corpus supplied no benign controls. */
        false_positive_rate: number | null;
      }
  );

export type CorpusEntry = {
  id: string;
  category: string;
  severity: string;
  target: string;
  description: string;
  forbidden_tools: string[];
  expects_canary: boolean;
  strategy: "static" | "sequence" | "adaptive";
  turns: number;
};

export const redTeam = (
  id: string,
  body: {
    categories?: string[];
    strategies?: Array<"static" | "sequence" | "adaptive">;
    model?: string;
  } = {},
) => post<RedTeamReport>(`/harnesses/${idPath(id)}/redteam`, body);

export const redTeamCorpus = () =>
  get<{
    count: number;
    categories: string[];
    strategies: string[];
    attacks: CorpusEntry[];
  }>(
    "/redteam/corpus",
  );

// ---------------------------------------------------------------------------
// judge calibration
// ---------------------------------------------------------------------------

export type Interval = {
  point: number;
  low: number;
  high: number;
  level: number;
  width: number;
  n: number;
};

export type CalibrationReport = {
  judge_id: string;
  certified: boolean;
  n: number;
  created_at: string;
  thresholds: {
    inter_rater_kappa: number;
    judge_spearman: number;
    sample_size: number;
  };
  threshold_source: string;
  rubric: {
    ok: boolean;
    raters: string[];
    cohens_kappa: Interval;
    weighted_kappa: number;
    percent_agreement: number;
    pairwise_kappa: Record<string, number>;
    interpretation: string;
  };
  judge: {
    ok: boolean;
    spearman: Interval;
    pearson: number;
    weighted_kappa: number;
    bias: number;
  } | null;
  human_scores: ScoreSummary;
  judge_scores: ScoreSummary | null;
  failures: string[];
  warnings: string[];
};

export type ScoreSummary = {
  n: number;
  mean: number;
  stdev: number;
  min: number;
  max: number;
  distribution: Record<string, number>;
};

export type LabelledCase = {
  id: string;
  output?: string;
  ratings: Record<string, number>;
  judge_score?: number;
};

export const calibrateJudge = (cases: LabelledCase[], resamples = 1000) =>
  post<CalibrationReport>("/judge/calibrate", { cases, resamples });

// ---------------------------------------------------------------------------
// governance
// ---------------------------------------------------------------------------

export type Control = {
  control: string;
  /** `supported` | `partial` | `missing` */
  status: string;
  evidence: string;
  /** Never empty. A mapping that lists only strengths is marketing. */
  gap: string;
};

export type GovernanceReport = {
  generated_at: string;
  workspace: string;
  summary: Record<string, number>;
  audit_log: {
    records: number;
    artifacts: number;
    total_cost_usd: number;
    oldest: string | null;
    newest: string | null;
    retention_days: number;
    path: string;
  };
  controls: Control[];
  disclaimer: string;
};

export const governanceReport = () => get<GovernanceReport>("/governance/report");

export type AuditStats = GovernanceReport["audit_log"] & {
  /** Distinguishes "never turned on" from "on, but nothing has run yet" — same zero. */
  audit_enabled: boolean;
  integrity?: {
    valid: boolean | null;
    status: string;
    hashed_records: number;
    legacy_unsealed_records: number;
    note: string;
  };
};

export const auditStats = () => get<AuditStats>("/audit");

export type AuditRecord = {
  timestamp: string;
  run_id: string;
  artifact_id: string;
  kind: string;
  version: number;
  outcome: string;
  model: string;
  provider: string;
  cost_usd: number;
  total_tokens: number;
  latency_ms: number;
  environment: string;
  actor: string;
};

export const auditLog = (opts: { artifactId?: string; limit?: number } = {}) => {
  const params = new URLSearchParams();
  if (opts.artifactId) params.set("artifact_id", opts.artifactId);
  params.set("limit", String(opts.limit ?? 1000));
  return get<{ count: number; records: AuditRecord[] }>(`/audit/log?${params}`);
};

export type ObservabilityStatus = {
  tracer_registered: boolean;
  otel_api_available: boolean;
  provider: string | null;
  recording_provider: boolean;
  otlp_endpoint_declared: boolean;
  content_capture: boolean;
  audit_enabled: boolean;
  export_verified: null;
  note: string;
};

export const observabilityStatus = () => get<ObservabilityStatus>("/observability");

// ---------------------------------------------------------------------------
// token economy
// ---------------------------------------------------------------------------

export type TokenReport = {
  prompts: number;
  index: {
    included: number;
    namespaces: Record<string, number>;
    omitted: string[];
    excluded_by_status: string[];
    truncated_summaries: string[];
    index_tokens: number;
    full_tokens: number;
    budget_tokens: number;
    saved_tokens: number;
    saving_ratio: number;
    tokens_per_entry: number;
  };
  heaviest: { id: string; tier1_tokens: number; tier2_tokens: number }[];
  naive_total_tokens: number;
  disclosed_tokens?: number;
};

export const tokenReport = () => get<TokenReport>("/tokens");
export const disclosureIndex = () => get<unknown>("/index");

// ---------------------------------------------------------------------------
// spec and plugins
// ---------------------------------------------------------------------------

export type JsonSchema = {
  $id?: string;
  title?: string;
  description?: string;
  required?: string[];
  properties?: Record<string, SchemaProperty>;
};

export type SchemaProperty = {
  type?: string | string[];
  description?: string;
  const?: unknown;
  enum?: unknown[];
  default?: unknown;
  pattern?: string;
  properties?: Record<string, SchemaProperty>;
  items?: SchemaProperty;
};

export const spec = () => get<JsonSchema>("/spec");

export type PluginEntry = {
  name: string;
  target: string;
  source: string;
  distribution: string | null;
  loaded: boolean;
  error: string | null;
};

export const plugins = () => get<Record<string, PluginEntry[]>>("/plugins");

export type GuardrailScan = {
  checked: true;
  recognised_risk: boolean;
  pii_count: number;
  pii_by_type: Record<string, number>;
  injection_detected: boolean;
  injection_flags: string[];
  findings: {
    category: "pii" | "injection";
    label: string;
    count: number;
    description: string;
  }[];
  note: string;
  limitations: string[];
};

export const scanGuardrails = (text: string) =>
  post<GuardrailScan>("/guardrails/scan", { text });

// ---------------------------------------------------------------------------
// evaluation
// ---------------------------------------------------------------------------

export type EvalReport = {
  passed: boolean;
  cases?: {
    id: string;
    passed: boolean;
    assertions?: { type: string; passed: boolean; reason: string }[];
  }[];
  environment?: { fingerprint: string; provider: string; deterministic: boolean };
  [k: string]: unknown;
};

export const health = () => get<{ status: string; [k: string]: unknown }>("/health");

// ---------------------------------------------------------------------------
// workspace health — everything the dashboard renders, in one call
// ---------------------------------------------------------------------------

/**
 * `"empty"` is not a failure. It means the workspace has nothing of this kind yet, and
 * the UI must show guidance rather than a zero — a zero implies a measurement was taken.
 */
export type SectionStatus = "ok" | "attention" | "empty";

export type WorkspaceHealth = {
  generated_at: string;
  workspace: { name: string; root: string; default_model: string | null };
  /** No artifacts at all — the page swaps to guided first steps. */
  is_new: boolean;
  needs_attention: string[];
  not_yet_used: string[];

  inventory: {
    total: number;
    kinds: Record<string, number>;
    namespaces: Record<string, number>;
    statuses: Record<string, number>;
    with_evals: number;
    without_evals: number;
    unreadable: { id: string; error: string }[];
    status: SectionStatus;
  };
  coverage: {
    total: number;
    tested: number;
    /** `null` when there is nothing to measure — undefined, not zero. */
    ratio: number | null;
    untested: string[];
    status: SectionStatus;
  };
  calibration: {
    judges: { id: string; certified: boolean; reason: string; uses_judge: boolean }[];
    certified: number;
    uncertified_in_use: number;
    status: SectionStatus;
    note: string;
  };
  security: {
    status: SectionStatus;
    usable?: boolean;
    /** Withheld (null) when the run produced no usable result. */
    attack_success_rate?: number | null;
    detection_rate?: number | null;
    mode?: string;
    mode_note?: string;
    created_at?: string;
    harness_id?: string;
    note?: string | null;
  };
  economy: {
    status: SectionStatus;
    prompts: number;
    index_tokens: number;
    full_tokens: number;
    saving_ratio: number | null;
    over_budget: boolean;
    note?: string;
  };
  spend: {
    status: SectionStatus;
    audit_enabled: boolean;
    records: number;
    total_cost_usd: number;
    oldest: string | null;
    newest: string | null;
    note: string | null;
  };
  plugins: {
    status: SectionStatus;
    groups: Record<string, number>;
    total: number;
    failures: { group: string; name: string; error: string }[];
  };
};

export const workspaceHealth = () =>
  request<WorkspaceHealth>("/workspace/health");

// ---------------------------------------------------------------------------
// starter packs
// ---------------------------------------------------------------------------

export type PackItem = {
  pack_id: string;
  id: string;
  name: string | null;
  summary: string;
  kind: string;
  tags: string[];
  status: string;
  variables: string[];
  has_evals: boolean;
  eval_scope: string;
  file: string;
  body_preview: string;
};

export type Pack = {
  id: string;
  name: string;
  count: number;
  categories: Record<string, number>;
  items: PackItem[];
  unreadable: { file: string; error: string }[];
};

export type InstallResult = {
  pack: string;
  installed: { id: string; path: string }[];
  skipped: { id: string; reason: string }[];
  failed: { file: string; error: string }[];
  counts: { installed: number; skipped: number; failed: number };
  note: string | null;
};

export const listPacks = () => get<{ packs: Pack[]; total: number }>("/packs");

// ---------------------------------------------------------------------------
// integrations — how the rest of the toolchain finds these prompts
// ---------------------------------------------------------------------------

export type AgentsMdPreview = {
  content: string;
  artifacts: number;
  targets: Record<
    string,
    { file: string; exists: boolean; has_generated_block: boolean }
  >;
  /** Tools that read AGENTS.md natively. */
  reaches: string[];
  note: string;
};

export type McpClient = {
  id: string;
  name: string;
  file: string;
  config: string;
  docs: string;
};

export type McpConfig = {
  workspace_root: string;
  clients: McpClient[];
  tools: { name: string; does: string }[];
  note: string;
};

export type ChatExport = {
  id: string;
  system: string;
  user: string;
  plain: string;
  with_settings: string;
  settings: string[];
  targets: { id: string; name: string; url: string }[];
  note: string;
};

export type ModelEntry = {
  ref: string;
  provider: string;
  id: string;
  name: string;
  context_window: number;
  max_output_tokens: number;
  input_cost_per_mtok: number;
  output_cost_per_mtok: number;
  capabilities: string[];
  deprecated: boolean;
};

export type ModelCatalogue = {
  count: number;
  providers: string[];
  models: ModelEntry[];
  synced_at: string | null;
  source: string | null;
  /** True when running on the small bundled seed — never synced. */
  is_seed: boolean;
  sources: Record<string, string>;
};

export type PromptSummary = {
  id: string;
  name: string | null;
  description: string;
  kind: string;
  status: string;
  version: number;
  model: string | null;
  tags: string[];
  variables: string[];
  has_evals: boolean;
};

export const listPrompts = () => get<PromptSummary[]>("/prompts");

export type CreatePromptRequest = {
  id: string;
  body: string;
  name?: string;
  description?: string;
  kind?: string;
  status?: string;
  tags?: string[];
  model?: string;
  commit_message?: string;
};

export const createPrompt = (payload: CreatePromptRequest) =>
  post<PromptSummary>("/prompts", payload);

export type PromptDetail = PromptSummary & {
  /** The raw PromptFile text — frontmatter plus body, exactly as it sits on disk. */
  source: string;
  document: Record<string, unknown>;
  required_capabilities: string[];
};

export const getPrompt = (id: string, version?: number) =>
  get<PromptDetail>(`/prompts/${idPath(id)}${version ? `?version=${version}` : ""}`);

export type PromptHistoryEntry = {
  version?: number;
  message?: string;
  timestamp?: string;
  [k: string]: unknown;
};

export const promptHistory = (id: string) =>
  get<{ id: string; history: PromptHistoryEntry[] }>(`/prompts/${idPath(id)}/history`);

export type RenderedMessage = { role: string; content: string; [k: string]: unknown };

export type RenderResult = {
  id: string;
  version: number;
  model: string | null;
  params: Record<string, unknown>;
  messages: RenderedMessage[];
};

export const renderPrompt = (id: string, variables: Record<string, unknown> = {}, model?: string) =>
  post<RenderResult>(`/prompts/${idPath(id)}/render`, { variables, model });

export const evaluatePrompt = (
  id: string,
  model?: string,
  judgeModel?: string,
  maxWorkers = 1,
) =>
  post<EvalReport>(
    `/prompts/${idPath(id)}/evaluate${
      model || judgeModel || maxWorkers !== 1
        ? `?${[model && `model=${encodeURIComponent(model)}`, judgeModel && `judge_model=${encodeURIComponent(judgeModel)}`, maxWorkers !== 1 && `max_workers=${maxWorkers}`]
            .filter(Boolean)
            .join("&")}`
        : ""
    }`,
  );

export type ExperimentVariant = {
  prompt_id: string;
  version?: number;
  model?: string;
};

export type ExperimentResult = {
  variant_a: { prompt_id: string; version: number; model: string | null; report: EvalReport };
  variant_b: { prompt_id: string; version: number; model: string | null; report: EvalReport };
  comparison: {
    usable: boolean;
    paired_cases: number;
    excluded_cases: string[];
    delta: number | null;
    delta_direction?: "b_minus_a";
    delta_ci: { low: number | null; high: number | null; level: number; method: string };
    winner: "a" | "b" | null;
    reason: string;
    cost_usd?: { a: number; b: number; total: number };
    note?: string;
  };
};

export const compareExperiment = (variantA: ExperimentVariant, variantB: ExperimentVariant) =>
  post<ExperimentResult>("/experiments/compare", {
    variant_a: variantA,
    variant_b: variantB,
  });

export type UpdatePromptRequest = {
  body?: string;
  name?: string;
  description?: string;
  status?: string;
  tags?: string[];
  model?: string;
  commit_message?: string;
};

export const updatePrompt = (id: string, payload: UpdatePromptRequest) =>
  request<PromptSummary>(`/prompts/${idPath(id)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const deletePrompt = (id: string) =>
  request<void>(`/prompts/${idPath(id)}`, { method: "DELETE" });

export const previewAgentsMd = () => get<AgentsMdPreview>("/integrations/agents-md");

export type ProviderStatus = {
  configured: number;
  total: number;
  providers: {
    id: string;
    label: string;
    configured: boolean;
    source: string;
  }[];
  note: string;
};

export const providerStatus = () =>
  get<ProviderStatus>("/integrations/provider-status");

export const writeAgentsMd = (targets: string[]) =>
  post<{ written: { file: string; created: boolean }[]; count: number }>(
    "/integrations/agents-md",
    { targets },
  );

export const mcpConfig = () => get<McpConfig>("/integrations/mcp");

export type Bundle = {
  id: string;
  name: string;
  kind: string;
  summary: string;
  skills: string[];
  path: string;
  readme: string;
  install: string[];
  why: string;
};

export const listBundles = () =>
  get<{ bundles: Bundle[]; count: number }>("/integrations/bundles");

export const exportForChat = (id: string, variables: Record<string, unknown> = {}) =>
  post<ChatExport>(`/integrations/export/${idPath(id)}`, { variables });

export const modelCatalogue = () => get<ModelCatalogue>("/integrations/models");
export const syncModels = () =>
  post<{ synced: number; providers: number; source: string; problems: string[] }>(
    "/integrations/models/sync",
  );

/** `ids` empty installs the whole pack. Existing files are skipped unless `overwrite`. */
export const installPack = (
  packId: string,
  ids: string[] = [],
  overwrite = false,
) => post<InstallResult>(`/packs/${encodeURIComponent(packId)}/install`, { ids, overwrite });

/**
 * Assay TypeScript SDK.
 *
 * Zero dependencies — uses the platform `fetch`, so it runs in Node 18+, Deno, Bun,
 * Cloudflare Workers, Vercel Edge, and the browser without a bundler shim.
 *
 * ```ts
 * import { Assay } from "assay";
 *
 * const assay = new Assay({ baseUrl: "http://127.0.0.1:8001" });
 * const { output, costUsd } = await assay.run("support/refund-triage", { message: "…" });
 * ```
 */

export interface MPLOptions {
  /** Base URL of a server exposing `/v1`. */
  baseUrl?: string;
  apiKey?: string;
  /** Request timeout in milliseconds. */
  timeoutMs?: number;
  /** Override for testing or for custom retry/proxy behaviour. */
  fetch?: typeof globalThis.fetch;
}

export interface PromptRef {
  id: string;
  name: string;
  description: string;
  version: number;
  kind: string;
  status: "draft" | "review" | "stable" | "deprecated" | "archived";
  tags: string[];
  model: string | null;
  variables: string[];
  hasEvals: boolean;
}

export interface Usage {
  inputTokens: number;
  outputTokens: number;
  cachedInputTokens: number;
  reasoningTokens: number;
  totalTokens: number;
}

export interface RunResult {
  runId: string;
  promptId: string;
  promptVersion: number;
  model: string;
  provider: string;
  output: string;
  toolCalls: Array<{ name: string; arguments: Record<string, unknown>; id: string | null }>;
  usage: Usage;
  latencyMs: number;
  costUsd: number;
  fallbackUsed: string | null;
  guardrailEvents: Array<{ stage: string; guardrail: string; action: string; reason: string }>;
}

export interface StreamEvent {
  type: "delta" | "tool_call_delta" | "completed";
  index: number;
  delta: string;
  toolCall?: {
    index: number;
    id: string | null;
    name: string;
    arguments: string | Record<string, unknown>;
  };
  buffered: boolean;
  result?: RunResult & { streaming?: Record<string, unknown> };
}

export interface EvalReport {
  promptId: string;
  promptVersion: number;
  model: string;
  passed: boolean;
  score: number;
  cases: Array<{
    id: string;
    passed: boolean;
    score?: number;
    output?: string;
    results: Array<{ evaluator: string; passed: boolean; score: number; reason: string }>;
  }>;
  totalAssertions: number;
  failedAssertions: number;
  totalCostUsd: number;
  execution?: {
    mode: "serial" | "bounded_concurrent";
    maxConcurrency: number;
    scheduledCases: number;
    wallclockMs: number;
  };
}

export class AssayError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "AssayError";
  }
}

/** Recursively convert snake_case keys to camelCase so the SDK feels native in TS. */
function camelize<T>(value: unknown): T {
  if (Array.isArray(value)) return value.map((v) => camelize(v)) as unknown as T;
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
      out[key.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase())] = camelize(val);
    }
    return out as T;
  }
  return value as T;
}

export class Assay {
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof globalThis.fetch;

  constructor(options: MPLOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://127.0.0.1:8001").replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.timeoutMs = options.timeoutMs ?? 120_000;
    this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis);
    if (!this.fetchImpl) {
      throw new AssayError("No fetch implementation available; pass one via options.fetch");
    }
  }

  private async request<T>(method: string, path: string, body?: unknown, query?: Record<string, unknown>): Promise<T> {
    const url = new URL(`${this.baseUrl}/v1${path}`);
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, String(v)));
      else url.searchParams.set(key, String(value));
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(url.toString(), {
        method,
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          "X-Assay-Api-Version": "1",
          ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {}),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });

      if (response.status === 204) return undefined as T;
      const payload = await response.json().catch(() => undefined);
      if (!response.ok) {
        throw new AssayError(`${method} ${path} → HTTP ${response.status}`, response.status, payload);
      }
      return camelize<T>(payload);
    } catch (error) {
      if (error instanceof AssayError) throw error;
      if ((error as Error).name === "AbortError") {
        throw new AssayError(`${method} ${path} timed out after ${this.timeoutMs}ms`);
      }
      throw new AssayError(`${method} ${path} failed: ${(error as Error).message}`);
    } finally {
      clearTimeout(timer);
    }
  }

  /** List prompts, optionally filtered. */
  list(filter: { prefix?: string; tag?: string[]; status?: string } = {}): Promise<PromptRef[]> {
    return this.request<PromptRef[]>("GET", "/prompts", undefined, filter);
  }

  /** Fetch one prompt, optionally at a historical version. */
  get(promptId: string, version?: number): Promise<PromptRef & { source: string; document: unknown }> {
    return this.request("GET", `/prompts/${promptId}`, undefined, { version });
  }

  /** Fill variables without calling a model. */
  render(
    promptId: string,
    variables: Record<string, unknown> = {},
    model?: string,
  ): Promise<{ model: string; messages: Array<{ role: string; content: string }> }> {
    return this.request("POST", `/prompts/${promptId}/render`, { variables, model });
  }

  /** Render and execute. */
  run(
    promptId: string,
    variables: Record<string, unknown> = {},
    options: { model?: string; params?: Record<string, unknown> } = {},
  ): Promise<RunResult> {
    return this.request<RunResult>("POST", `/prompts/${promptId}/run`, {
      variables,
      model: options.model,
      params: options.params ?? {},
    });
  }

  /** Stream text/tool-call deltas followed by one completed event with run evidence. */
  async *stream(
    promptId: string,
    variables: Record<string, unknown> = {},
    options: { model?: string; params?: Record<string, unknown> } = {},
  ): AsyncGenerator<StreamEvent> {
    const url = `${this.baseUrl}/v1/prompts/${promptId}/stream`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(url, {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          "X-Assay-Api-Version": "1",
          ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {}),
        },
        body: JSON.stringify({
          variables,
          model: options.model,
          params: options.params ?? {},
        }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new AssayError(
          `POST /prompts/${promptId}/stream → HTTP ${response.status}`,
          response.status,
          detail.slice(0, 500),
        );
      }
      if (!response.body) throw new AssayError("Streaming response has no body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split(/\r?\n/);
        buffer = done ? "" : lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trim();
          if (data === "[DONE]") return;
          const event = JSON.parse(data) as { type: string; error?: unknown };
          if (event.type === "error") {
            throw new AssayError("Stream failed", undefined, event.error);
          }
          yield camelize<StreamEvent>(event);
        }
        if (done) return;
      }
    } catch (error) {
      if (error instanceof AssayError) throw error;
      if ((error as Error).name === "AbortError") {
        throw new AssayError(`Stream timed out after ${this.timeoutMs}ms`);
      }
      throw new AssayError(`Stream failed: ${(error as Error).message}`);
    } finally {
      clearTimeout(timer);
    }
  }

  /** Run the prompt's embedded eval cases. Use this as a deploy gate. */
  evaluate(
    promptId: string,
    options: { model?: string; maxWorkers?: number } = {},
  ): Promise<EvalReport> {
    return this.request<EvalReport>("POST", `/prompts/${promptId}/evaluate`, undefined, {
      model: options.model,
      max_workers: options.maxWorkers,
    });
  }

  create(promptId: string, body: string, fields: Partial<PromptRef> & { commitMessage?: string } = {}): Promise<PromptRef> {
    return this.request<PromptRef>("POST", "/prompts", { id: promptId, body, ...fields });
  }

  update(promptId: string, changes: Partial<PromptRef> & { body?: string }): Promise<PromptRef> {
    return this.request<PromptRef>("PATCH", `/prompts/${promptId}`, changes);
  }

  models(provider?: string): Promise<{ count: number; models: Array<Record<string, unknown>> }> {
    return this.request("GET", "/models", undefined, { provider });
  }

  health(): Promise<{ status: string; apiVersion: string; coreVersion: string }> {
    return this.request("GET", "/health");
  }
}

export default Assay;

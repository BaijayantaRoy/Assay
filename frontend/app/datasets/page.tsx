"use client";

import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Database, FlaskConical, Play, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorPanel, Loading, PageHeader } from "@/components/v1/shell";
import { EvalReport, PromptSummary, evaluatePrompt, listPrompts } from "@/lib/v1";

type Interval = {
  low?: number | null;
  high?: number | null;
  usable_cases?: number;
  method?: string;
  reason?: string;
};

export default function EvalLabPage() {
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [model, setModel] = useState("");
  const [report, setReport] = useState<EvalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    listPrompts()
      .then((items) => {
        setPrompts(items);
        setSelected(items.find((item) => item.has_evals)?.id || "");
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const tested = useMemo(() => prompts.filter((prompt) => prompt.has_evals), [prompts]);

  async function run() {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setReport(null);
    try {
      setReport(await evaluatePrompt(selected, model.trim() || undefined));
    } catch (problem) {
      setError(problem);
    } finally {
      setRunning(false);
    }
  }

  if (loading) return <Loading label="Loading eval-bearing PromptFiles…" />;

  const interval = report?.score_ci as Interval | undefined;
  const score = numberOrNull(report?.score);
  const total = numberOrNull(report?.total_assertions);
  const failed = numberOrNull(report?.failed_assertions);
  const unverified = numberOrNull(report?.unverified_cases);
  const cost = numberOrNull(report?.total_cost_usd);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        icon={FlaskConical}
        title="Eval Lab"
        subtitle="Run PromptFile evals through the same engine as the CLI and MCP server."
        note={
          <>
            Datasets are workspace-relative JSONL or JSON files referenced by{" "}
            <code className="font-mono">evals[].dataset</code>. Inline and external cases
            share denominators, uncertainty, and failure attribution. There is no shadow
            SQL dataset catalogue.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <Card>
        <CardContent className="p-5 space-y-4">
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
            <label className="space-y-1.5 text-xs text-muted-foreground">
              PromptFile with evals
              <select
                value={selected}
                onChange={(event) => setSelected(event.target.value)}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground"
              >
                {tested.map((prompt) => (
                  <option key={prompt.id} value={prompt.id}>{prompt.id}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5 text-xs text-muted-foreground">
              Model override (optional)
              <Input
                value={model}
                onChange={(event) => setModel(event.target.value)}
                placeholder="provider/model"
              />
            </label>
            <Button onClick={run} disabled={!selected || running} className="gap-2">
              <Play className={["h-4 w-4", running ? "animate-pulse" : ""].join(" ")} />
              {running ? "Running…" : "Run evals"}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {tested.length} of {prompts.length} artifacts carry eval cases.
          </p>
        </CardContent>
      </Card>

      {tested.length === 0 && (
        <Card>
          <CardContent className="p-12 text-center text-muted-foreground">
            <Database className="h-12 w-12 mx-auto mb-3 opacity-25" />
            <p className="font-medium text-foreground">Nothing is testable yet</p>
            <p className="text-sm mt-1">
              Add an eval case to the PromptFile source under <code className="font-mono">prompts/</code>,
              then return here to run it.
            </p>
          </CardContent>
        </Card>
      )}

      {report && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Metric label="Result" value={report.passed ? "PASS" : "FAIL"} tone={report.passed ? "good" : "bad"} />
            <Metric label="Score" value={score == null ? "withheld" : percent(score)} />
            <Metric label="Usable cases" value={String(interval?.usable_cases ?? "—")} />
            <Metric label="Assertions" value={total == null ? "—" : String(total - (failed ?? 0)) + "/" + String(total)} />
            <Metric label="Measured cost" value={cost == null ? "—" : "$" + cost.toFixed(6)} />
          </div>

          <Card>
            <CardContent className="p-5 grid gap-3 text-xs md:grid-cols-3">
              <Evidence label="95% score interval" value={intervalText(interval)} />
              <Evidence label="Interval method" value={interval?.method || "withheld"} />
              <Evidence label="Unverified cases" value={String(unverified ?? 0)} />
            </CardContent>
          </Card>

          <div className="space-y-2">
            {(report.cases || []).map((caseResult) => (
              <Card key={caseResult.id}>
                <CardContent className="p-4 flex items-start gap-3">
                  {caseResult.passed
                    ? <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5" />
                    : <XCircle className="h-4 w-4 text-red-400 mt-0.5" />}
                  <div>
                    <p className="text-sm font-medium">{caseResult.id}</p>
                    {(caseResult.assertions || []).map((assertion, index) => (
                      <p key={assertion.type + String(index)} className="text-[11px] text-muted-foreground mt-1">
                        {assertion.passed ? "pass" : "fail"} · {assertion.type} · {assertion.reason}
                      </p>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function percent(value: number): string {
  return (value * 100).toFixed(1) + "%";
}

function intervalText(interval?: Interval): string {
  if (interval?.low == null || interval?.high == null) {
    return "withheld — " + (interval?.reason || "insufficient usable cases");
  }
  return percent(interval.low) + "–" + percent(interval.high);
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad";
}) {
  const color = tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-red-400" : "";
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[10px] uppercase text-muted-foreground">{label}</p>
        <p className={["text-lg font-bold mt-1", color].join(" ")}>{value}</p>
      </CardContent>
    </Card>
  );
}

function Evidence({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/25 p-3">
      <p className="text-muted-foreground">{label}</p>
      <p className="mt-1 font-medium text-foreground">{value}</p>
    </div>
  );
}

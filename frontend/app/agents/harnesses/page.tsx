"use client";

/**
 * Harnesses — run an agent and read its trajectory.
 *
 * The output is the least interesting part of an agent run and the only part most tools
 * show. What matters is the path: which tools were called, what came back, what was
 * denied, and where the budget went. This page puts the trajectory first and the answer
 * second, because a right answer reached through a denied tool call is still a bug.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  Bot, Play, Wrench, ShieldAlert, Coins, Repeat, ChevronRight,
  CircleDot, AlertTriangle, Eye, Brain, CheckCircle2,
  Radio,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Empty, ErrorPanel, Loading, PageHeader, Stat, VerifiedMark, shortId,
} from "@/components/v1/shell";
import { HowTo } from "@/components/v1/howto";
import {
  HarnessSummary, Trajectory, TrajectoryStep, listHarnesses, runHarness,
} from "@/lib/v1";

const STATUS_TONE: Record<string, string> = {
  completed: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  max_iterations: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  budget_exceeded: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  denied: "text-orange-400 bg-orange-500/10 border-orange-500/30",
  failed: "text-red-400 bg-red-500/10 border-red-500/30",
};

export default function HarnessesPage() {
  const [harnesses, setHarnesses] = useState<HarnessSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [goal, setGoal] = useState("find the retry logic");
  const [dryRun, setDryRun] = useState(false);
  const [trajectory, setTrajectory] = useState<Trajectory | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listHarnesses()
      .then((h) => {
        setHarnesses(h);
        if (h.length) setSelected(h[0].id);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const run = useCallback(async () => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setTrajectory(null);
    try {
      setTrajectory(
        await runHarness(selected, { goal, variables: { topic: goal }, dry_run: dryRun }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }, [selected, goal, dryRun]);

  if (loading) return <Loading label="Loading harnesses…" />;

  const current = harnesses.find((h) => h.id === selected);

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={Bot}
        title="Harnesses"
        subtitle="Agent loops with tools, budgets, memory and control mechanisms"
        gradient="from-violet-500/10 via-blue-500/5"
        iconGradient="from-violet-500 to-blue-500"
        border="border-violet-500/20"
        note={
          <>
            A harness is the four elements of an agent — the loop, the tool interface,
            context management and the control mechanisms — declared in one file. Every
            run below produces a <strong>trajectory</strong>: the record of what the agent
            actually did. Assertions run against the trajectory, not just the final text,
            because an agent can reach the right answer the wrong way.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <HowTo concept="harness" />

      {!harnesses.length && !error ? (
        <Empty
          icon={Bot}
          title="No harnesses in this workspace"
          hint={
            <>
              Create one with <code className="font-mono">assay new --kind harness</code>,
              or copy <code className="font-mono">prompts/agents/researcher.prompt.md</code>.
            </>
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
          {/* ------------------------------------------------ picker */}
          <div className="space-y-3">
            {harnesses.map((h) => (
              <Card
                key={h.id}
                onClick={() => setSelected(h.id)}
                className={`cursor-pointer transition-all ${
                  selected === h.id
                    ? "border-violet-500/50 bg-violet-500/5"
                    : "hover:border-border/80"
                }`}
              >
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-sm truncate">{h.name || h.id}</p>
                    <Badge variant="outline" className="text-[10px] shrink-0">
                      v{h.version}
                    </Badge>
                  </div>
                  <p className="text-[11px] font-mono text-muted-foreground truncate">
                    {h.id}
                  </p>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {h.tools.map((t) => (
                      <span
                        key={t}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground pt-1">
                    <span className="flex items-center gap-1">
                      <Repeat className="h-3 w-3" />
                      max {h.max_iterations ?? "—"}
                    </span>
                    {h.memory && (
                      <span className="flex items-center gap-1 text-violet-400">
                        <Brain className="h-3 w-3" />
                        memory
                      </span>
                    )}
                    {h.has_evals && (
                      <span className="flex items-center gap-1 text-emerald-400">
                        <CheckCircle2 className="h-3 w-3" />
                        evals
                      </span>
                    )}
                    {h.stream_model_calls && (
                      <span className="flex items-center gap-1 text-cyan-400">
                        <Radio className="h-3 w-3" />
                        streamed
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* ------------------------------------------------ runner */}
          <div className="space-y-4">
            <Card>
              <CardContent className="p-5 space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-medium text-muted-foreground">
                    Goal
                  </label>
                  <Input
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    placeholder="What should the agent achieve?"
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={dryRun}
                      onChange={(e) => setDryRun(e.target.checked)}
                      className="accent-violet-500"
                    />
                    <Eye className="h-3.5 w-3.5" />
                    Dry run — read-only controller, no side effects
                  </label>
                  <Button onClick={run} disabled={running || !selected} className="gap-2">
                    <Play className={`h-4 w-4 ${running ? "animate-pulse" : ""}`} />
                    {running ? "Running…" : "Run harness"}
                  </Button>
                </div>
                {current && (
                  <p className="text-[11px] text-muted-foreground border-t border-border pt-3">
                    Budget: {current.budget.cost_usd != null && `$${current.budget.cost_usd} · `}
                    {current.budget.wallclock_s != null && `${current.budget.wallclock_s}s · `}
                    {current.budget.tool_calls != null && `${current.budget.tool_calls} tool calls`}
                    {" — the run stops when the first of these is reached."}
                  </p>
                )}
              </CardContent>
            </Card>

            {trajectory && <TrajectoryView t={trajectory} />}
          </div>
        </div>
      )}
    </div>
  );
}

function TrajectoryView({ t }: { t: Trajectory }) {
  const tone = STATUS_TONE[t.status] || "text-muted-foreground bg-muted border-border";
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Iterations" value={t.iterations} hint={`of ${t.budget.iterations ?? "—"} allowed`} />
        <Stat label="Tool calls" value={t.tool_calls.length} hint={t.tool_errors ? `${t.tool_errors} errored` : "none errored"} tone={t.tool_errors ? "warn" : "default"} />
        <Stat label="Cost" value={`$${t.cost_usd.toFixed(4)}`} hint={`${t.total_tokens.toLocaleString()} tokens`} />
        <Stat label="Wallclock" value={`${t.wallclock_s.toFixed(3)}s`} hint={t.model} />
      </div>

      <Card>
        <CardContent className="p-5 space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${tone}`}>
                {t.status}
              </span>
              <VerifiedMark verified={t.verified} detail={t.verification_detail} />
            </div>
            <span className="text-[11px] font-mono text-muted-foreground">
              run {shortId(t.run_id)}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            <span className="font-medium">Stopped because:</span> {t.stop_reason}
          </p>
          {t.denied_calls.length > 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-orange-500/30 bg-orange-500/5 p-3">
              <ShieldAlert className="h-4 w-4 text-orange-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-orange-400">
                  {t.denied_calls.length} call{t.denied_calls.length > 1 ? "s" : ""} denied by the controller
                </p>
                <p className="text-[11px] text-muted-foreground font-mono">
                  {t.denied_calls.join(", ")}
                </p>
              </div>
            </div>
          )}
          <div className="rounded-lg bg-muted/50 p-3">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">
              Final output
            </p>
            <p className="text-sm whitespace-pre-wrap">{t.output || "(empty)"}</p>
          </div>
        </CardContent>
      </Card>

      <div>
        <div className="flex items-center gap-2 mb-3">
          <CircleDot className="h-4 w-4 text-violet-400" />
          <h2 className="text-sm font-semibold">Trajectory</h2>
          <span className="text-[11px] text-muted-foreground">
            {t.steps.length} steps — tool output is fenced as untrusted data before it
            re-enters the context
          </span>
        </div>
        <div className="space-y-2">
          {t.steps.map((s) => (
            <StepRow key={s.index} step={s} />
          ))}
        </div>
      </div>
    </div>
  );
}

function StepRow({ step }: { step: TrajectoryStep }) {
  const [open, setOpen] = useState(false);
  const hasDetail = step.tool_results.length > 0;
  return (
    <Card className={hasDetail ? "cursor-pointer" : ""}>
      <CardContent className="p-4" onClick={() => hasDetail && setOpen(!open)}>
        <div className="flex items-start gap-3">
          <span className="mt-0.5 h-6 w-6 shrink-0 rounded-full bg-muted flex items-center justify-center text-[11px] font-mono">
            {step.index}
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-sm">{step.text || <em className="text-muted-foreground">no text</em>}</p>
            {step.tool_calls.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {step.tool_calls.map((c) => (
                  <span
                    key={c.id}
                    className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20 font-mono"
                  >
                    <Wrench className="h-3 w-3" />
                    {c.name}
                  </span>
                ))}
              </div>
            )}
            {step.context_action && (
              <p className="text-[11px] text-amber-400">
                context: {step.context_action} ({step.context_tokens.toLocaleString()} tokens)
              </p>
            )}
            {step.streaming && (
              <p className="text-[11px] text-cyan-400 flex items-center gap-1">
                <Radio className="h-3 w-3" />
                {step.streaming.mode} provider stream · {step.streaming.chunks_received} chunk
                {step.streaming.chunks_received === 1 ? "" : "s"}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0 text-[11px] text-muted-foreground">
            {step.cost_usd > 0 && (
              <span className="flex items-center gap-1">
                <Coins className="h-3 w-3" />${step.cost_usd.toFixed(4)}
              </span>
            )}
            {hasDetail && (
              <ChevronRight
                className={`h-4 w-4 transition-transform ${open ? "rotate-90" : ""}`}
              />
            )}
          </div>
        </div>

        {open && (
          <div className="mt-3 pl-9 space-y-2">
            {step.tool_results.map((r, i) => (
              <div
                key={i}
                className={`rounded-lg border p-3 ${
                  r.denied
                    ? "border-orange-500/30 bg-orange-500/5"
                    : r.is_error
                      ? "border-red-500/30 bg-red-500/5"
                      : "border-border bg-muted/40"
                }`}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="font-mono text-[11px] font-semibold">{r.tool}</span>
                  {r.denied && (
                    <Badge variant="outline" className="text-[10px] text-orange-400 border-orange-500/40">
                      denied
                    </Badge>
                  )}
                  {r.is_error && (
                    <Badge variant="outline" className="text-[10px] text-red-400 border-red-500/40">
                      error
                    </Badge>
                  )}
                  <span className="text-[10px] text-muted-foreground ml-auto">
                    {r.latency_ms}ms
                  </span>
                </div>
                <p className="text-[11px] font-mono text-muted-foreground mb-1.5">
                  {JSON.stringify(r.arguments)}
                </p>
                <p className="text-xs whitespace-pre-wrap break-words">{r.content}</p>
                {r.denied_reason && (
                  <p className="text-[11px] text-orange-400 mt-1.5 flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    {r.denied_reason}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

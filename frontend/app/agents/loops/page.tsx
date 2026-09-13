"use client";

/**
 * Loops — outer-loop engineering, with verification made visible.
 *
 * The design decision this page exists to expose: verification happens at every handoff,
 * not only at the end. Errors compound — a 90%-accurate step feeding another 90%-accurate
 * step does not yield 90% — so by step 18 of a 20-step chain you can have a confident,
 * coherent, wrong result that a single final check would happily pass. Each step therefore
 * carries its own verification mark, and a cycle that passes overall while an intermediate
 * step failed is rendered as the warning it is.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  RefreshCw, Play, Target, GitBranch, Terminal, AlertTriangle, Ban,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Empty, ErrorPanel, Loading, PageHeader, Stat, VerifiedMark, shortId,
} from "@/components/v1/shell";
import { HowTo } from "@/components/v1/howto";
import { LoopCycle, LoopRun, LoopSummary, listLoops, runLoop } from "@/lib/v1";

/**
 * Status copy. `stalled` is deliberately distinguished from a plain failure: verification
 * failing means the work was wrong, stalling means the work did not change at all. The
 * fixes are different, so the labels are too.
 */
const STATUS: Record<string, { cls: string; blurb: string }> = {
  goal_met: {
    cls: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
    blurb: "The goal condition verified. The loop stopped immediately rather than burning remaining cycles.",
  },
  stalled: {
    cls: "text-amber-400 bg-amber-500/10 border-amber-500/30",
    blurb: "Output stopped changing between cycles. Continuing would cost money and change nothing, so the loop stopped early.",
  },
  max_cycles: {
    cls: "text-orange-400 bg-orange-500/10 border-orange-500/30",
    blurb: "The cycle budget ran out before the goal verified.",
  },
  failed: {
    cls: "text-red-400 bg-red-500/10 border-red-500/30",
    blurb: "A step failed and the loop was configured to stop there.",
  },
};

export default function LoopsPage() {
  const [loops, setLoops] = useState<LoopSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<LoopRun | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listLoops()
      .then((l) => {
        setLoops(l);
        if (l.length) setSelected(l[0].id);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const execute = useCallback(async () => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setRun(null);
    try {
      setRun(await runLoop(selected));
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }, [selected]);

  if (loading) return <Loading label="Loading loops…" />;

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={RefreshCw}
        title="Loops"
        subtitle="Outer loops with per-step verification and stall detection"
        gradient="from-cyan-500/10 via-teal-500/5"
        iconGradient="from-cyan-500 to-teal-500"
        border="border-cyan-500/20"
        note={
          <>
            A loop runs steps, verifies, and decides whether to go again. Verification runs
            at <strong>every handoff</strong>, not only at the end — errors compound, and a
            single final check will happily pass a chain that went wrong in the middle. A
            loop that declares no verification is marked <em>not checked</em>; it is never
            allowed to report success by default.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <HowTo concept="loop" />

      {!loops.length && !error ? (
        <Empty
          icon={RefreshCw}
          title="No loops in this workspace"
          hint={
            <>
              See <code className="font-mono">prompts/loops/verified-pipeline.prompt.md</code>{" "}
              for a worked example.
            </>
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
          <div className="space-y-3">
            {loops.map((l) => (
              <Card
                key={l.id}
                onClick={() => setSelected(l.id)}
                className={`cursor-pointer transition-all ${
                  selected === l.id ? "border-cyan-500/50 bg-cyan-500/5" : "hover:border-border/80"
                }`}
              >
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-sm truncate">{l.name || l.id}</p>
                    <Badge variant="outline" className="text-[10px] shrink-0">
                      v{l.version}
                    </Badge>
                  </div>
                  <p className="text-[11px] font-mono text-muted-foreground truncate">{l.id}</p>
                  <p className="text-xs text-muted-foreground flex items-start gap-1.5">
                    <Target className="h-3 w-3 mt-0.5 shrink-0" />
                    <span className="line-clamp-2">{l.goal}</span>
                  </p>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground pt-1">
                    <span className="flex items-center gap-1">
                      <GitBranch className="h-3 w-3" />
                      {l.steps} steps
                    </span>
                    <span>max {l.max_cycles} cycles</span>
                    {!l.has_verification && (
                      <span className="text-amber-400 flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        unverified
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="space-y-4">
            <Card>
              <CardContent className="p-5 flex items-center justify-between gap-4">
                <p className="text-xs text-muted-foreground">
                  Runs the loop against the workspace. Steps execute real commands in the
                  workspace root.
                </p>
                <Button onClick={execute} disabled={running || !selected} className="gap-2 shrink-0">
                  <Play className={`h-4 w-4 ${running ? "animate-pulse" : ""}`} />
                  {running ? "Running…" : "Run loop"}
                </Button>
              </CardContent>
            </Card>

            {run && <LoopRunView run={run} />}
          </div>
        </div>
      )}
    </div>
  );
}

function LoopRunView({ run }: { run: LoopRun }) {
  const status = STATUS[run.status] || {
    cls: "text-muted-foreground bg-muted border-border",
    blurb: "",
  };
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Cycles" value={run.cycle_count} hint="stops as soon as the goal verifies" />
        <Stat
          label="Goal met"
          value={run.goal_met ? "yes" : "no"}
          tone={run.goal_met ? "good" : "bad"}
        />
        <Stat label="Cost" value={`$${run.cost_usd.toFixed(4)}`} />
        <Stat label="Wallclock" value={`${run.wallclock_s.toFixed(3)}s`} />
      </div>

      <Card>
        <CardContent className="p-5 space-y-2">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${status.cls}`}>
              {run.status}
            </span>
            <span className="text-[11px] font-mono text-muted-foreground">
              run {shortId(run.run_id)}
            </span>
          </div>
          {status.blurb && (
            <p className="text-xs text-muted-foreground">{status.blurb}</p>
          )}
          <p className="text-[11px] font-mono text-muted-foreground break-words border-t border-border pt-2">
            {run.stop_reason}
          </p>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {run.cycles.map((c) => (
          <CycleView key={c.cycle} cycle={c} />
        ))}
      </div>
    </div>
  );
}

function CycleView({ cycle }: { cycle: LoopCycle }) {
  /**
   * The case worth shouting about: the cycle-level check passed, but an intermediate step
   * did not. `verified` says fine; the handoff says otherwise. Without this the final pass
   * hides the broken middle — which is precisely why step-level verification exists.
   */
  const brokenHandoff = cycle.steps.find((s) => s.verified === false);
  const hidesFailure = cycle.verified === true && brokenHandoff;

  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold">Cycle {cycle.cycle}</p>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground">
              {cycle.wallclock_s.toFixed(3)}s
            </span>
            <VerifiedMark verified={cycle.verified} detail={cycle.verification_detail} />
          </div>
        </div>

        {hidesFailure && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-xs text-muted-foreground">
              The cycle check passed, but step{" "}
              <code className="font-mono text-amber-400">{brokenHandoff!.id}</code> did not
              verify. A final pass can hide a broken intermediate handoff — this is the
              case step-level verification is for.
            </p>
          </div>
        )}

        <div className="space-y-2">
          {cycle.steps.map((s) => (
            <div key={s.id} className="rounded-lg border border-border bg-muted/30 p-3 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold font-mono">{s.id}</span>
                <div className="flex items-center gap-2">
                  {s.failed && (
                    <Badge variant="outline" className="text-[10px] text-red-400 border-red-500/40">
                      <Ban className="h-3 w-3 mr-1" />
                      failed
                    </Badge>
                  )}
                  <span className="text-[10px] text-muted-foreground">
                    exit {s.exit_code ?? "—"}
                  </span>
                  <VerifiedMark verified={s.verified} detail={s.verification_detail} />
                </div>
              </div>
              {s.command && (
                <p className="text-[11px] font-mono text-muted-foreground flex items-start gap-1.5 break-all">
                  <Terminal className="h-3 w-3 mt-0.5 shrink-0" />
                  {s.command}
                </p>
              )}
              {s.output && (
                <pre className="text-[11px] font-mono whitespace-pre-wrap bg-background/60 rounded p-2 max-h-32 overflow-auto">
                  {s.output}
                </pre>
              )}
              {s.verification_detail && (
                <p className="text-[10px] font-mono text-muted-foreground">
                  {s.verification_detail}
                </p>
              )}
            </div>
          ))}
        </div>

        {cycle.verification_detail && (
          <p className="text-[11px] font-mono text-muted-foreground border-t border-border pt-2">
            cycle check: {cycle.verification_detail}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

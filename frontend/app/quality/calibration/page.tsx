"use client";

/**
 * Judge calibration — a two-stage gate.
 *
 * Stage 1 measures agreement between the *human* raters. If humans disagree about what the
 * rubric means, calibrating a judge against their labels measures nothing at all, so the
 * gate stops there rather than reporting a judge score that looks fine. Stage 2 measures
 * the judge against the human consensus.
 *
 * Intervals are shown beside every point estimate on purpose. At small n the interval is
 * the real result — a κ of 0.83 spanning [0.10, 0.98] is not a calibrated judge, it is a
 * sample size problem wearing a number.
 */

import React, { useCallback, useState } from "react";
import {
  Gauge, Play, Users, Scale, AlertTriangle, CheckCircle2, XCircle,
  Plus, Trash2, Sparkles,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorPanel, PageHeader } from "@/components/v1/shell";
import { HowTo } from "@/components/v1/howto";
import {
  CalibrationReport, Interval, LabelledCase, ScoreSummary, calibrateJudge,
} from "@/lib/v1";

type Row = { id: string; a: number; b: number; judge: number };

/** Deterministic sample so the page demonstrates the gate without inventing evidence. */
function sampleRows(): Row[] {
  const base = [4, 2, 5, 3, 1, 4, 3, 5, 2, 4, 1, 3, 5, 4, 2, 3, 4, 1, 5, 2, 3, 4, 2, 5];
  return base.map((v, i) => ({
    id: `case-${i + 1}`,
    a: v,
    b: Math.min(5, Math.max(1, v + (i % 5 === 0 ? 1 : 0))),
    judge: Math.min(5, Math.max(1, v + (i % 3 === 0 ? 1 : 0))),
  }));
}

export default function CalibrationPage() {
  const [rows, setRows] = useState<Row[]>(sampleRows());
  const [report, setReport] = useState<CalibrationReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(async () => {
    setRunning(true);
    setError(null);
    setReport(null);
    try {
      const cases: LabelledCase[] = rows.map((r) => ({
        id: r.id,
        ratings: { rater_a: r.a, rater_b: r.b },
        judge_score: r.judge,
      }));
      setReport(await calibrateJudge(cases, 1000));
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }, [rows]);

  const update = (i: number, key: keyof Row, value: number) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [key]: value } : r)));

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={Gauge}
        title="Judge Calibration"
        subtitle="Prove an LLM judge agrees with humans before trusting its scores"
        gradient="from-amber-500/10 via-yellow-500/5"
        iconGradient="from-amber-500 to-yellow-500"
        border="border-amber-500/20"
        note={
          <>
            An uncalibrated judge is a random number generator with good manners. This runs
            a two-stage gate: first Cohen&apos;s κ between human raters — because if the
            humans disagree the rubric is ambiguous and nothing downstream means anything —
            then Spearman&apos;s ρ between the judge and their consensus. Confidence
            intervals come from bootstrap resampling, and at small n the{" "}
            <strong>interval is the result</strong>.
          </>
        }
        action={
          <Button onClick={run} disabled={running || rows.length < 3} className="gap-2 shrink-0">
            <Play className={`h-4 w-4 ${running ? "animate-pulse" : ""}`} />
            {running ? "Calibrating…" : "Run calibration"}
          </Button>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <HowTo concept="calibration" />

      <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-6">
        {/* ---------------------------------------------------- input */}
        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">Labelled cases</p>
              <div className="flex gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1 h-7 text-[11px]"
                  onClick={() => setRows(sampleRows())}
                >
                  <Sparkles className="h-3 w-3" />
                  Sample
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1 h-7 text-[11px]"
                  onClick={() =>
                    setRows((rs) => [
                      ...rs,
                      { id: `case-${rs.length + 1}`, a: 3, b: 3, judge: 3 },
                    ])
                  }
                >
                  <Plus className="h-3 w-3" />
                  Row
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-[1fr_44px_44px_44px_24px] gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground px-1">
              <span>case</span>
              <span className="text-center">A</span>
              <span className="text-center">B</span>
              <span className="text-center">judge</span>
              <span />
            </div>

            <div className="space-y-1 max-h-[440px] overflow-auto pr-1">
              {rows.map((r, i) => (
                <div
                  key={i}
                  className="grid grid-cols-[1fr_44px_44px_44px_24px] gap-1.5 items-center"
                >
                  <span className="text-[11px] font-mono truncate text-muted-foreground">
                    {r.id}
                  </span>
                  {(["a", "b", "judge"] as const).map((k) => (
                    <input
                      key={k}
                      type="number"
                      min={1}
                      max={5}
                      value={r[k]}
                      onChange={(e) => update(i, k, Number(e.target.value))}
                      className={`h-7 w-full rounded border border-border bg-background text-center text-[11px] ${
                        k === "judge" ? "text-amber-400" : ""
                      }`}
                    />
                  ))}
                  <button
                    onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                    className="text-muted-foreground hover:text-red-400"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>

            <p className="text-[10px] text-muted-foreground border-t border-border pt-2">
              Two human raters (A, B) and the judge score each case 1–5. The published
              threshold is 500 cases; anything smaller is reported with a warning rather
              than silently accepted.
            </p>
          </CardContent>
        </Card>

        {/* ---------------------------------------------------- report */}
        <div className="space-y-4">
          {!report ? (
            <Card className="border-dashed">
              <CardContent className="p-10 text-center space-y-2">
                <Gauge className="h-8 w-8 mx-auto text-muted-foreground/40" />
                <p className="text-sm text-muted-foreground">
                  Run calibration to see whether this judge can be trusted.
                </p>
              </CardContent>
            </Card>
          ) : (
            <ReportView report={report} />
          )}
        </div>
      </div>
    </div>
  );
}

function ReportView({ report }: { report: CalibrationReport }) {
  return (
    <>
      <Card className={report.certified ? "border-emerald-500/40" : "border-amber-500/40"}>
        <CardContent className="p-5 flex items-start gap-3">
          {report.certified ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
          ) : (
            <XCircle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
          )}
          <div className="space-y-1.5 min-w-0">
            <p
              className={`text-sm font-semibold ${
                report.certified ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {report.certified ? "Judge certified" : "Not certified"}
            </p>
            {report.failures.map((f) => (
              <p key={f} className="text-xs text-muted-foreground">
                {f}
              </p>
            ))}
            {report.warnings.map((w) => (
              <p key={w} className="text-xs text-amber-400/80 flex items-start gap-1.5">
                <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                {w}
              </p>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* stage 1 */}
      <Card>
        <CardContent className="p-5 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-400" />
              Stage 1 — do the humans agree?
            </p>
            <GateBadge ok={report.rubric.ok} />
          </div>
          <p className="text-xs text-muted-foreground">
            If this fails, stop. A judge calibrated against an ambiguous rubric inherits the
            ambiguity and hides it behind a number.
          </p>
          <IntervalBar
            label="Cohen's κ"
            interval={report.rubric.cohens_kappa}
            threshold={report.thresholds.inter_rater_kappa}
          />
          <div className="grid grid-cols-3 gap-3 pt-1">
            <MiniStat label="Weighted κ" value={report.rubric.weighted_kappa.toFixed(3)} hint="near-misses penalised less" />
            <MiniStat label="Exact agreement" value={`${(report.rubric.percent_agreement * 100).toFixed(1)}%`} />
            <MiniStat label="Interpretation" value={report.rubric.interpretation} />
          </div>
          <p className="text-[10px] text-muted-foreground">
            Raters: {report.rubric.raters.join(", ")}
          </p>
        </CardContent>
      </Card>

      {/* stage 2 */}
      {report.judge && (
        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold flex items-center gap-2">
                <Scale className="h-4 w-4 text-amber-400" />
                Stage 2 — does the judge track the consensus?
              </p>
              <GateBadge ok={report.judge.ok} />
            </div>
            <IntervalBar
              label="Spearman's ρ"
              interval={report.judge.spearman}
              threshold={report.thresholds.judge_spearman}
            />
            <div className="grid grid-cols-3 gap-3 pt-1">
              <MiniStat label="Pearson r" value={report.judge.pearson.toFixed(3)} />
              <MiniStat label="Weighted κ" value={report.judge.weighted_kappa.toFixed(3)} />
              <MiniStat
                label="Bias"
                value={report.judge.bias > 0 ? `+${report.judge.bias.toFixed(3)}` : report.judge.bias.toFixed(3)}
                hint={report.judge.bias > 0 ? "scores high" : report.judge.bias < 0 ? "scores low" : "unbiased"}
              />
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Distribution title="Human consensus" summary={report.human_scores} tone="bg-blue-500/60" />
        {report.judge_scores && (
          <Distribution title="Judge scores" summary={report.judge_scores} tone="bg-amber-500/60" />
        )}
      </div>

      <Card className="bg-muted/30">
        <CardContent className="p-4">
          <p className="text-[10px] text-muted-foreground leading-relaxed">
            <span className="font-semibold">On the thresholds:</span> {report.threshold_source}
          </p>
        </CardContent>
      </Card>
    </>
  );
}

function GateBadge({ ok }: { ok: boolean }) {
  return (
    <Badge
      variant="outline"
      className={`text-[10px] ${ok ? "text-emerald-400 border-emerald-500/40" : "text-red-400 border-red-500/40"}`}
    >
      {ok ? "pass" : "fail"}
    </Badge>
  );
}

/**
 * Renders the interval as a bar and the threshold as a line across it. A point estimate
 * sitting above the threshold while its lower bound sits below is the single most common
 * way calibration results get over-read, and drawing both makes that visible at a glance.
 */
function IntervalBar({
  label,
  interval,
  threshold,
}: {
  label: string;
  interval: Interval;
  threshold: number;
}) {
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  const lo = clamp(interval.low);
  const hi = clamp(interval.high);
  const point = clamp(interval.point);
  const straddles = interval.low < threshold && interval.point >= threshold;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium">{label}</span>
        <span className="font-mono">
          {interval.point.toFixed(3)}{" "}
          <span className="text-muted-foreground">
            [{interval.low.toFixed(3)}, {interval.high.toFixed(3)}]
          </span>
        </span>
      </div>
      <div className="relative h-6 rounded bg-muted overflow-hidden">
        <div
          className="absolute inset-y-0 bg-blue-500/25"
          style={{ left: `${lo * 100}%`, width: `${Math.max(0.5, (hi - lo) * 100)}%` }}
        />
        <div
          className="absolute inset-y-0 w-0.5 bg-blue-400"
          style={{ left: `${point * 100}%` }}
        />
        <div
          className="absolute inset-y-0 w-0.5 bg-red-400/80"
          style={{ left: `${clamp(threshold) * 100}%` }}
          title={`threshold ${threshold}`}
        />
      </div>
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>
          {(interval.level * 100).toFixed(0)}% CI · n={interval.n} · width{" "}
          {interval.width.toFixed(3)}
        </span>
        <span>threshold {threshold}</span>
      </div>
      {straddles && (
        <p className="text-[10px] text-amber-400 flex items-start gap-1">
          <AlertTriangle className="h-3 w-3 mt-px shrink-0" />
          The point estimate clears the threshold but the interval does not. Collect more
          cases before calling this settled.
        </p>
      )}
    </div>
  );
}

function MiniStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm font-semibold font-mono">{value}</p>
      {hint && <p className="text-[10px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Distribution({
  title,
  summary,
  tone,
}: {
  title: string;
  summary: ScoreSummary;
  tone: string;
}) {
  const entries = Object.entries(summary.distribution).sort(
    (a, b) => Number(a[0]) - Number(b[0]),
  );
  const max = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">{title}</p>
          <span className="text-[10px] font-mono text-muted-foreground">
            μ {summary.mean.toFixed(2)} · σ {summary.stdev.toFixed(2)}
          </span>
        </div>
        <div className="flex items-end gap-1 h-24">
          {entries.map(([score, count]) => (
            <div key={score} className="flex-1 flex flex-col items-center gap-1">
              <div className="w-full flex items-end h-full">
                <div
                  className={`w-full rounded-t ${tone}`}
                  style={{ height: `${(count / max) * 100}%` }}
                  title={`${count} case${count === 1 ? "" : "s"}`}
                />
              </div>
              <span className="text-[9px] text-muted-foreground font-mono">{score}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

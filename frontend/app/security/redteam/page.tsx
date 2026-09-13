"use client";

/**
 * Red team — indirect prompt injection, measured honestly.
 *
 * The dangerous number in this product is a 0% attack-success rate produced by a run where
 * nothing actually executed. That is a false green, and it is exactly what a security
 * dashboard is supposed to prevent rather than manufacture. So `usable` is checked before
 * any rate is rendered: if every attack errored, this page refuses to show a score at all.
 *
 * The second honesty problem is `mode`. Against an offline provider these numbers measure
 * the *defences* — fence, detector, controls — not whether a real model would comply. That
 * distinction is stated on the page, not buried in a tooltip.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  Swords, Play, ShieldCheck, ShieldAlert, Bug, FlaskConical, Info, XCircle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Empty, ErrorPanel, Loading, PageHeader, Stat, pct,
} from "@/components/v1/shell";
import { HowTo } from "@/components/v1/howto";
import {
  AttackResult, CorpusEntry, HarnessSummary, RedTeamReport,
  listHarnesses, redTeam, redTeamCorpus,
} from "@/lib/v1";

const SEVERITY: Record<string, string> = {
  critical: "text-red-400 border-red-500/40",
  high: "text-orange-400 border-orange-500/40",
  medium: "text-amber-400 border-amber-500/40",
  low: "text-blue-400 border-blue-500/40",
};

export default function RedTeamPage() {
  const [harnesses, setHarnesses] = useState<HarnessSummary[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [corpus, setCorpus] = useState<{ count: number; categories: string[]; attacks: CorpusEntry[] } | null>(null);
  const [report, setReport] = useState<RedTeamReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([listHarnesses(), redTeamCorpus()])
      .then(([h, c]) => {
        setHarnesses(h);
        setCorpus(c);
        if (h.length) setSelected(h[0].id);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const run = useCallback(async () => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setReport(null);
    try {
      setReport(await redTeam(selected));
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }, [selected]);

  if (loading) return <Loading label="Loading corpus…" />;

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={Swords}
        title="Red Team"
        subtitle="Indirect prompt injection against a harness, scored against a versioned corpus"
        gradient="from-red-500/10 via-orange-500/5"
        iconGradient="from-red-500 to-orange-500"
        border="border-red-500/20"
        note={
          <>
            Attacks arrive through <strong>tool output</strong> — the realistic path, since
            that is content the agent did not write and cannot vouch for. The corpus carries
            benign controls alongside the attacks so a detector that flags everything scores
            badly rather than perfectly. None of this is safety: it raises the cost of an
            attack, it does not close the class.
          </>
        }
        action={
          <div className="flex items-center gap-2 shrink-0">
            <select
              aria-label="Harness to red-team"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="h-9 rounded-md border border-border bg-background px-3 text-xs"
            >
              {harnesses.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.id}
                </option>
              ))}
            </select>
            <Button onClick={run} disabled={running || !selected} className="gap-2">
              <Play className={`h-4 w-4 ${running ? "animate-pulse" : ""}`} />
              {running ? "Running…" : "Run corpus"}
            </Button>
          </div>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <HowTo concept="redteam" />

      {corpus && !report && (
        <CorpusView corpus={corpus} />
      )}

      {report && <ReportView report={report} />}

      {!harnesses.length && !error && (
        <Empty icon={Swords} title="No harnesses to attack" hint="Red-teaming targets a harness — create one first." />
      )}
    </div>
  );
}

function CorpusView({
  corpus,
}: {
  corpus: { count: number; categories: string[]; attacks: CorpusEntry[] };
}) {
  const benign = corpus.attacks.filter((a) => a.category === "benign").length;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Corpus entries" value={corpus.count} hint="versioned with the spec" />
        <Stat label="Attacks" value={corpus.count - benign} />
        <Stat
          label="Benign controls"
          value={benign}
          hint="catch a detector that flags everything"
        />
        <Stat label="Categories" value={corpus.categories.length} />
      </div>

      <Card>
        <CardContent className="p-5">
          <p className="text-sm font-semibold mb-3">Attack corpus v1</p>
          <div className="space-y-2">
            {corpus.attacks.map((a) => (
              <div
                key={a.id}
                className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-3"
              >
                <Badge
                  variant="outline"
                  className={`text-[10px] shrink-0 ${SEVERITY[a.severity] || ""}`}
                >
                  {a.severity}
                </Badge>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-[11px] font-semibold">{a.id}</span>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {a.category}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                      via {a.target}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{a.description}</p>
                  {a.forbidden_tools.length > 0 && (
                    <p className="text-[10px] font-mono text-red-400 mt-1">
                      compromised if it calls: {a.forbidden_tools.join(", ")}
                    </p>
                  )}
                  {a.expects_canary && (
                    <p className="text-[10px] font-mono text-red-400 mt-1">
                      compromised if the canary leaks
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ReportView({ report }: { report: RedTeamReport }) {
  /**
   * Gate on `usable` before showing a single rate. A run where every attack errored has an
   * attack-success rate of 0.0 arithmetically and no meaning whatsoever.
   */
  if (!report.usable) {
    return (
      <Card className="border-red-500/40 bg-red-500/5">
        <CardContent className="p-6 space-y-3">
          <div className="flex items-center gap-2">
            <XCircle className="h-5 w-5 text-red-400" />
            <p className="font-semibold text-red-400">This run produced no usable result</p>
          </div>
          <p className="text-sm text-muted-foreground">
            {report.errored} of {report.attacks_run} attacks errored before they could be
            scored. The rates are being withheld deliberately: a run where nothing executed
            reports a 0% attack-success rate, and showing that would be worse than showing
            nothing.
          </p>
          {report.errors.length > 0 && (
            <pre className="text-[11px] font-mono bg-background/60 rounded p-3 max-h-48 overflow-auto whitespace-pre-wrap">
              {report.errors.join("\n")}
            </pre>
          )}
        </CardContent>
      </Card>
    );
  }

  const asrTone = report.attack_success_rate > 0 ? "bad" : "good";
  const falsePositiveRate = report.false_positive_rate;

  return (
    <div className="space-y-4">
      {report.mode === "scripted" && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="p-4 flex items-start gap-2">
            <Info className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="text-xs font-semibold text-amber-400">
                Scripted run — this measures the defences, not model susceptibility
              </p>
              <p className="text-[11px] text-muted-foreground">
                {report.mode_note} To measure whether a real model complies, re-run with a
                live provider.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Attack success rate"
          value={pct(report.attack_success_rate)}
          hint={`${report.attacks_run} attacks run`}
          tone={asrTone}
        />
        <Stat
          label="Detection rate"
          value={pct(report.detection_rate)}
          hint="attacks the scanner flagged"
          tone={report.detection_rate >= 0.6 ? "good" : "warn"}
        />
        <Stat
          label="False positives"
          value={falsePositiveRate == null ? "Not checked" : pct(falsePositiveRate)}
          hint={falsePositiveRate == null
            ? "no benign controls in this corpus"
            : `${report.benign_controls} benign controls`}
          tone={falsePositiveRate != null && falsePositiveRate > 0 ? "warn" : "good"}
        />
        <Stat
          label="Errored"
          value={report.errored}
          hint={report.errored ? "excluded from the rates" : "all attacks scored"}
          tone={report.errored ? "warn" : "default"}
        />
      </div>

      <Card className={report.passed ? "border-emerald-500/30" : "border-red-500/40"}>
        <CardContent className="p-5 flex items-start gap-3">
          {report.passed ? (
            <ShieldCheck className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
          ) : (
            <ShieldAlert className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          )}
          <div className="space-y-1 min-w-0">
            <p className={`text-sm font-semibold ${report.passed ? "text-emerald-400" : "text-red-400"}`}>
              {report.passed ? "No attack compromised the harness" : `${report.compromised.length} attacks succeeded`}
            </p>
            <p className="text-[11px] text-muted-foreground font-mono break-all">
              {report.harness_id} · {report.model} · {new Date(report.created_at).toLocaleString()}
            </p>
            <p className="text-[11px] text-muted-foreground">
              Detection sits below 100% by design — the obfuscation, staged and
              false-authority categories are known gaps, and are listed as gaps rather than
              quietly excluded from the denominator.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5">
          <p className="text-sm font-semibold mb-3 flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-red-400" />
            By category
          </p>
          <div className="space-y-2">
            {Object.entries(report.by_category).map(([cat, stats]) => {
              const detection = stats.total ? stats.detected / stats.total : 0;
              const isBenign = cat === "benign";
              return (
                <div key={cat} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono">{cat}</span>
                    <span className="text-muted-foreground">
                      {isBenign ? (
                        <>
                          {stats.detected}/{stats.total} flagged{" "}
                          <span className={stats.detected ? "text-amber-400" : "text-emerald-400"}>
                            ({stats.detected ? "false positives" : "clean"})
                          </span>
                        </>
                      ) : (
                        <>
                          {stats.detected}/{stats.total} detected ·{" "}
                          <span className={stats.compromised ? "text-red-400" : "text-emerald-400"}>
                            {stats.compromised} compromised
                          </span>
                        </>
                      )}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full ${
                        isBenign
                          ? stats.detected
                            ? "bg-amber-500"
                            : "bg-emerald-500/40"
                          : detection >= 0.999
                            ? "bg-emerald-500"
                            : detection > 0
                              ? "bg-amber-500"
                              : "bg-red-500"
                      }`}
                      style={{ width: `${(isBenign ? (stats.detected / stats.total) : detection) * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5">
          <p className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Bug className="h-4 w-4 text-red-400" />
            Individual results
          </p>
          <div className="space-y-1.5">
            {report.results.map((r) => (
              <AttackRow key={r.id} result={r} />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function AttackRow({ result }: { result: AttackResult }) {
  const tone =
    result.outcome === "compromised"
      ? "border-red-500/40 bg-red-500/5"
      : result.outcome === "errored"
        ? "border-amber-500/40 bg-amber-500/5"
        : "border-border bg-muted/30";
  return (
    <div className={`flex items-center gap-3 rounded-lg border p-2.5 ${tone}`}>
      <span className="font-mono text-[11px] font-semibold w-16 shrink-0">{result.id}</span>
      <span className="text-[10px] text-muted-foreground font-mono w-40 shrink-0 truncate">
        {result.category}
      </span>
      <Badge variant="outline" className={`text-[10px] shrink-0 ${SEVERITY[result.severity] || ""}`}>
        {result.severity}
      </Badge>
      <span className="flex-1" />
      {result.detected != null && (
        <span
          className={`text-[10px] ${result.detected ? "text-blue-400" : "text-muted-foreground"}`}
        >
          {result.detected ? "flagged" : "not flagged"}
        </span>
      )}
      <span
        className={`text-[11px] font-medium shrink-0 ${
          result.outcome === "compromised"
            ? "text-red-400"
            : result.outcome === "errored"
              ? "text-amber-400"
              : "text-emerald-400"
        }`}
      >
        {result.outcome}
      </span>
    </div>
  );
}

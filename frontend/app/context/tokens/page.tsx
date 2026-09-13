"use client";

/**
 * Token economy — what progressive disclosure actually saves.
 *
 * Loading every prompt into an agent's context so it can pick one is the default failure
 * mode, and it is expensive: context is a budget, not a bucket. Three-tier loading means
 * an agent sees a compact index first and pulls the full body only for what it chose.
 *
 * The saving is reported as a measurement of this workspace, not as a marketing figure —
 * which is why the naive total is shown beside it. A ratio without its denominator is a
 * claim.
 */

import React, { useEffect, useState } from "react";
import { Coins, Layers, TrendingDown, FileWarning, Package } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorPanel, Loading, PageHeader, Stat, pct } from "@/components/v1/shell";
import { HowTo } from "@/components/v1/howto";
import { TokenReport, tokenReport } from "@/lib/v1";

export default function TokensPage() {
  const [report, setReport] = useState<TokenReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    tokenReport().then(setReport).catch(setError).finally(() => setLoading(false));
  }, []);

  if (loading) return <Loading label="Counting tokens…" />;

  const idx = report?.index;
  const overBudget = idx ? idx.index_tokens > idx.budget_tokens : false;

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={Coins}
        title="Token Economy"
        subtitle="Progressive disclosure — what an agent loads, and what it costs"
        gradient="from-emerald-500/10 via-teal-500/5"
        iconGradient="from-emerald-500 to-teal-500"
        border="border-emerald-500/20"
        note={
          <>
            Context is a budget, not a bucket. Tier 1 is a compact index every agent can
            afford to hold; tier 2 is the full artifact, fetched only for what the agent
            picked. The saving below is measured against{" "}
            <strong>this workspace</strong>, not quoted from a benchmark — the naive total
            is shown so the ratio can be checked.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <HowTo concept="tokens" />

      {report && idx && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat
              label="Saving"
              value={pct(idx.saving_ratio)}
              hint={`${idx.saved_tokens.toLocaleString()} tokens not loaded`}
              tone="good"
            />
            <Stat
              label="Index"
              value={idx.index_tokens.toLocaleString()}
              hint={`budget ${idx.budget_tokens.toLocaleString()}`}
              tone={overBudget ? "bad" : "default"}
            />
            <Stat
              label="Naive total"
              value={report.naive_total_tokens.toLocaleString()}
              hint="every artifact, fully loaded"
            />
            <Stat
              label="Per entry"
              value={idx.tokens_per_entry.toFixed(1)}
              hint={`${idx.included} of ${report.prompts} artifacts indexed`}
            />
          </div>

          {/* -------------------------------------------------- the bar */}
          <Card>
            <CardContent className="p-5 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold flex items-center gap-2">
                  <TrendingDown className="h-4 w-4 text-emerald-400" />
                  Index versus everything
                </p>
                <span className="text-xs font-mono text-muted-foreground">
                  {idx.index_tokens.toLocaleString()} / {idx.full_tokens.toLocaleString()}
                </span>
              </div>
              <div className="h-8 rounded-lg bg-muted overflow-hidden flex">
                <div
                  className="bg-emerald-500 flex items-center justify-center"
                  style={{ width: `${Math.max(2, (idx.index_tokens / idx.full_tokens) * 100)}%` }}
                >
                  <span className="text-[10px] font-semibold text-white px-1 truncate">
                    tier 1
                  </span>
                </div>
                <div className="flex-1 flex items-center justify-center">
                  <span className="text-[10px] text-muted-foreground">
                    tier 2 — loaded on demand only
                  </span>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                An agent that reads the index instead of the whole library spends{" "}
                {pct(1 - idx.saving_ratio)} of the tokens it otherwise would. That headroom
                goes to the actual task.
              </p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* ------------------------------------------- heaviest */}
            <Card>
              <CardContent className="p-5 space-y-3">
                <p className="text-sm font-semibold flex items-center gap-2">
                  <Package className="h-4 w-4 text-emerald-400" />
                  Heaviest artifacts
                </p>
                <div className="space-y-2.5">
                  {report.heaviest.map((h) => {
                    const max = Math.max(
                      ...report.heaviest.map((x) => x.tier1_tokens + x.tier2_tokens),
                    );
                    return (
                      <div key={h.id} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono truncate">{h.id}</span>
                          <span className="text-muted-foreground shrink-0 ml-2">
                            {h.tier1_tokens} → {h.tier2_tokens.toLocaleString()}
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-muted overflow-hidden flex">
                          <div
                            className="bg-emerald-500"
                            style={{ width: `${(h.tier1_tokens / max) * 100}%` }}
                            title={`tier 1: ${h.tier1_tokens} tokens`}
                          />
                          <div
                            className="bg-emerald-500/25"
                            style={{ width: `${(h.tier2_tokens / max) * 100}%` }}
                            title={`tier 2: ${h.tier2_tokens} tokens`}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
                <p className="text-[10px] text-muted-foreground border-t border-border pt-2">
                  Solid = what the index costs. Faded = what is deferred until the agent
                  asks for it.
                </p>
              </CardContent>
            </Card>

            {/* ------------------------------------------- namespaces */}
            <Card>
              <CardContent className="p-5 space-y-3">
                <p className="text-sm font-semibold flex items-center gap-2">
                  <Layers className="h-4 w-4 text-emerald-400" />
                  Namespaces
                </p>
                <div className="space-y-2">
                  {Object.entries(idx.namespaces).map(([ns, count]) => (
                    <div key={ns} className="flex items-center justify-between text-xs">
                      <span className="font-mono">{ns}</span>
                      <span className="text-muted-foreground">
                        {count} artifact{count === 1 ? "" : "s"}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="text-[10px] text-muted-foreground border-t border-border pt-2">
                  The namespace map lets an agent narrow before it fetches — the second
                  half of progressive disclosure.
                </p>
              </CardContent>
            </Card>
          </div>

          {/* -------------------------------------------------- omissions */}
          {(idx.omitted.length > 0 ||
            idx.excluded_by_status.length > 0 ||
            idx.truncated_summaries.length > 0) && (
            <Card className="border-amber-500/30">
              <CardContent className="p-5 space-y-3">
                <p className="text-sm font-semibold flex items-center gap-2">
                  <FileWarning className="h-4 w-4 text-amber-400" />
                  What did not make the index
                </p>
                <p className="text-xs text-muted-foreground">
                  Reported rather than silently dropped. An agent that cannot see an
                  artifact will never choose it, so an omission is a behaviour change.
                </p>
                {idx.omitted.length > 0 && (
                  <Omission label="Omitted — budget reached" items={idx.omitted} />
                )}
                {idx.excluded_by_status.length > 0 && (
                  <Omission label="Excluded by status" items={idx.excluded_by_status} />
                )}
                {idx.truncated_summaries.length > 0 && (
                  <Omission label="Summary truncated" items={idx.truncated_summaries} />
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function Omission({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="space-y-1">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="flex flex-wrap gap-1">
        {items.map((i) => (
          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono">
            {i}
          </span>
        ))}
      </div>
    </div>
  );
}

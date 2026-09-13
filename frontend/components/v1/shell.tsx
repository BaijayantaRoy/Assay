"use client";

/**
 * Shared furniture for the `/v1` pages.
 *
 * These pages all have the same shape — call an endpoint, show a result, explain what the
 * result means — and the explanation is the point. A trajectory or an attack-success rate
 * is not self-evident the way a list of prompts is, so `PageHeader` takes a `note` and the
 * pages use it rather than leaving a number to be guessed at.
 */

import React from "react";
import { AlertTriangle, Loader2, ServerCrash } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { V1Error } from "@/lib/v1";

export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  note,
  gradient = "from-violet-500/10 via-blue-500/5",
  iconGradient = "from-violet-500 to-blue-500",
  border = "border-violet-500/20",
  action,
}: {
  icon: React.ElementType;
  title: string;
  subtitle: string;
  /** One line of context a reader needs to interpret what this page shows. */
  note?: React.ReactNode;
  gradient?: string;
  iconGradient?: string;
  border?: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      className={`p-8 rounded-2xl bg-gradient-to-br ${gradient} to-transparent border ${border}`}
    >
      <div className="flex items-start justify-between gap-6">
        <div className="flex items-center gap-3">
          <div
            className={`h-10 w-10 shrink-0 rounded-xl bg-gradient-to-br ${iconGradient} flex items-center justify-center`}
          >
            <Icon className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold">{title}</h1>
            <p className="text-muted-foreground text-sm">{subtitle}</p>
          </div>
        </div>
        {action}
      </div>
      {note && (
        <p className="mt-4 text-xs text-muted-foreground max-w-3xl leading-relaxed">
          {note}
        </p>
      )}
    </div>
  );
}

/**
 * An error surface that says what to do about it.
 *
 * "Failed to fetch" is not actionable. A connection refused on this product almost always
 * means the backend is not running, so say that instead of making the reader deduce it.
 */
export function ErrorPanel({ error }: { error: unknown }) {
  const v1 = error instanceof V1Error ? error : null;
  const unreachable = v1?.status === 0;
  return (
    <Card className="border-red-500/30 bg-red-500/5">
      <CardContent className="p-5 flex items-start gap-3">
        <ServerCrash className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
        <div className="space-y-1 min-w-0">
          <p className="text-sm font-semibold text-red-400">
            {unreachable ? "The API is not responding" : "Request failed"}
          </p>
          <p className="text-sm text-muted-foreground break-words">
            {error instanceof Error ? error.message : String(error)}
          </p>
          {unreachable && (
            <p className="text-xs text-muted-foreground pt-1">
              Start it with{" "}
              <code className="px-1 py-0.5 rounded bg-muted font-mono">
                start-assay.bat
              </code>{" "}
              — or run the backend directly on port 8001.
            </p>
          )}
          {v1?.code && (
            <p className="text-[11px] font-mono text-muted-foreground pt-1">
              {v1.code}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground py-10 justify-center">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

export function Empty({
  icon: Icon = AlertTriangle,
  title,
  hint,
}: {
  icon?: React.ElementType;
  title: string;
  hint?: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="p-10 text-center space-y-2">
        <Icon className="h-8 w-8 mx-auto text-muted-foreground/50" />
        <p className="text-sm font-medium">{title}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    default: "",
    good: "text-emerald-400",
    warn: "text-amber-400",
    bad: "text-red-400",
  }[tone];
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className={`text-2xl font-bold mt-1 ${toneClass}`}>{value}</p>
        {hint && (
          <p className="text-[11px] text-muted-foreground mt-1 leading-snug">{hint}</p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Tri-state verification: passed, failed, or *never checked*.
 *
 * The third state is why this exists. Rendering `null` as a failure would be wrong, and
 * rendering it as a pass would let a loop that verified nothing look like a loop that
 * verified everything — which is the exact failure mode the engine refuses to allow.
 */
export function VerifiedMark({
  verified,
  detail,
}: {
  verified: boolean | null;
  detail?: string;
}) {
  const map = {
    true: { text: "verified", cls: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" },
    false: { text: "failed", cls: "text-red-400 bg-red-500/10 border-red-500/30" },
    null: { text: "not checked", cls: "text-muted-foreground bg-muted/40 border-border" },
  }[String(verified) as "true" | "false" | "null"];
  return (
    <span
      title={detail || undefined}
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${map.cls}`}
    >
      {map.text}
    </span>
  );
}

/** Percentages read as percentages. `0.625` is a detection rate; `62.5%` is a finding. */
export const pct = (n: number, digits = 1) => `${(n * 100).toFixed(digits)}%`;

export const shortId = (id: string) => (id.length > 8 ? id.slice(0, 8) : id);

"use client";

/**
 * Governance — control mapping and the run log.
 *
 * The design constraint: every control states a gap, and the gap is rendered as
 * prominently as the evidence. A mapping that lists only strengths is marketing, and
 * assessors read it as marketing. Showing the gaps is what makes the evidence worth
 * anything.
 *
 * The disclaimer is not fine print either. This is a mapping of what the tool records; it
 * is not a compliance assessment, and nothing here should let someone believe they have
 * been audited.
 */

import React, { useEffect, useState } from "react";
import {
  Landmark, FileText, Clock, HardDrive, ShieldCheck, AlertCircle, MinusCircle, Info,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorPanel, Loading, PageHeader, Stat } from "@/components/v1/shell";
import { HowTo } from "@/components/v1/howto";
import { Control, GovernanceReport, governanceReport } from "@/lib/v1";

const STATUS_META: Record<
  string,
  { icon: React.ElementType; cls: string; label: string }
> = {
  supported: {
    icon: ShieldCheck,
    cls: "text-emerald-400 border-emerald-500/30 bg-emerald-500/5",
    label: "supported",
  },
  partial: {
    icon: AlertCircle,
    cls: "text-amber-400 border-amber-500/30 bg-amber-500/5",
    label: "partial",
  },
  missing: {
    icon: MinusCircle,
    cls: "text-red-400 border-red-500/30 bg-red-500/5",
    label: "missing",
  },
};

export default function GovernancePage() {
  const [report, setReport] = useState<GovernanceReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    governanceReport().then(setReport).catch(setError).finally(() => setLoading(false));
  }, []);

  if (loading) return <Loading label="Building control report…" />;

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={Landmark}
        title="Governance"
        subtitle="What this workspace records, mapped to the controls people are asked about"
        gradient="from-slate-500/10 via-blue-500/5"
        iconGradient="from-slate-500 to-blue-500"
        border="border-slate-500/20"
        note={
          <>
            Mapped against EU AI Act Articles 11, 12, 14 and 15, ISO 42001 §8.3 and §9.1,
            and the NIST AI RMF. Every control below states its <strong>gap</strong>
            alongside its evidence — a mapping that lists only strengths tells an assessor
            nothing except that you were selling.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <HowTo concept="governance" />

      {report && (
        <>
          <Card className="border-amber-500/30 bg-amber-500/5">
            <CardContent className="p-4 flex items-start gap-2">
              <Info className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-xs text-muted-foreground">{report.disclaimer}</p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat
              label="Supported"
              value={report.summary.supported ?? 0}
              tone="good"
              hint="control fully met by the tool"
            />
            <Stat
              label="Partial"
              value={report.summary.partial ?? 0}
              tone="warn"
              hint="tool contributes; operator must finish the job"
            />
            <Stat
              label="Missing"
              value={report.summary.missing ?? 0}
              tone={report.summary.missing ? "bad" : "default"}
            />
            <Stat
              label="Audit records"
              value={report.audit_log.records}
              hint={
                report.audit_log.records
                  ? `$${report.audit_log.total_cost_usd.toFixed(4)} logged`
                  : "auditing is off by default"
              }
            />
          </div>

          {/* --------------------------------------------------- run log */}
          <Card>
            <CardContent className="p-5 space-y-3">
              <p className="text-sm font-semibold flex items-center gap-2">
                <FileText className="h-4 w-4 text-blue-400" />
                Run log
              </p>
              {report.audit_log.records === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No records. Auditing is off unless the workspace asks for it — an audit
                  log nobody configured is a surprise file in someone&apos;s repository.
                  Enable it in <code className="font-mono">assay.yaml</code> under{" "}
                  <code className="font-mono">governance.audit</code>.
                </p>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                  <div>
                    <p className="text-muted-foreground">Artifacts</p>
                    <p className="font-semibold">{report.audit_log.artifacts}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Oldest</p>
                    <p className="font-semibold">
                      {report.audit_log.oldest
                        ? new Date(report.audit_log.oldest).toLocaleDateString()
                        : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Newest</p>
                    <p className="font-semibold">
                      {report.audit_log.newest
                        ? new Date(report.audit_log.newest).toLocaleDateString()
                        : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Total cost</p>
                    <p className="font-semibold">
                      ${report.audit_log.total_cost_usd.toFixed(4)}
                    </p>
                  </div>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground border-t border-border pt-3">
                <span className="flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />
                  Retention {report.audit_log.retention_days} days — clears the six-month
                  floor in Art. 12
                </span>
                <span className="flex items-center gap-1.5 font-mono break-all">
                  <HardDrive className="h-3 w-3 shrink-0" />
                  {report.audit_log.path}
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Prompt and completion content is excluded by default. A six-month log of
                every input and output is a liability, not an asset — it has to be opted
                into.
              </p>
            </CardContent>
          </Card>

          {/* --------------------------------------------------- controls */}
          <div className="space-y-3">
            <h2 className="text-sm font-semibold">Controls</h2>
            {report.controls.map((c) => (
              <ControlCard key={c.control} control={c} />
            ))}
          </div>

          <p className="text-[10px] text-muted-foreground text-center">
            Generated {new Date(report.generated_at).toLocaleString()} for workspace{" "}
            <code className="font-mono">{report.workspace}</code>
          </p>
        </>
      )}
    </div>
  );
}

function ControlCard({ control }: { control: Control }) {
  const meta = STATUS_META[control.status] || STATUS_META.partial;
  const Icon = meta.icon;
  return (
    <Card className={meta.cls.split(" ").filter((c) => c.startsWith("border")).join(" ")}>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-start gap-3">
          <Icon className={`h-4 w-4 shrink-0 mt-0.5 ${meta.cls.split(" ")[0]}`} />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">{control.control}</p>
          </div>
          <span
            className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${meta.cls}`}
          >
            {meta.label}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pl-7">
          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wide text-emerald-400/80">
              Evidence
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {control.evidence}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wide text-amber-400/80">Gap</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{control.gap}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

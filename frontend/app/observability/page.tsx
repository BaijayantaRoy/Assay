"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, CircleAlert, Clock, DollarSign, Hash, RadioTower, ShieldCheck } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { ErrorPanel, Loading, PageHeader } from "@/components/v1/shell";
import {
  auditLog,
  auditStats,
  observabilityStatus,
  type AuditRecord,
  type AuditStats,
  type ObservabilityStatus,
} from "@/lib/v1";

export default function ObservabilityPage() {
  const [status, setStatus] = useState<ObservabilityStatus | null>(null);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([observabilityStatus(), auditStats(), auditLog({ limit: 100 })])
      .then(([telemetry, audit, log]) => {
        setStatus(telemetry);
        setStats(audit);
        setRecords(log.records);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const summary = useMemo(() => ({
    tokens: records.reduce((total, record) => total + record.total_tokens, 0),
    cost: records.reduce((total, record) => total + record.cost_usd, 0),
    latency: records.length
      ? records.reduce((total, record) => total + record.latency_ms, 0) / records.length
      : null,
  }), [records]);

  if (loading) return <Loading label="Reading local telemetry evidence…" />;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        icon={Activity}
        title="Observability"
        subtitle="Local audit evidence and OpenTelemetry export readiness—without claiming collector delivery."
      />

      {error != null && <ErrorPanel error={error} />}

      {!status || !stats ? null : (
        <>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric icon={Activity} label="Audited runs" value={stats.audit_enabled ? String(stats.records) : "Not enabled"} />
        <Metric icon={Hash} label="Recorded tokens" value={stats.audit_enabled ? summary.tokens.toLocaleString() : "Not checked"} />
        <Metric icon={DollarSign} label="Recorded cost" value={stats.audit_enabled ? `$${summary.cost.toFixed(4)}` : "Not checked"} />
        <Metric icon={Clock} label="Average latency" value={summary.latency == null ? "Not checked" : `${summary.latency.toFixed(0)} ms`} />
      </div>

      <Card>
        <CardContent className="p-5 space-y-4">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 className="font-semibold flex items-center gap-2"><RadioTower className="h-4 w-4 text-primary" />OpenTelemetry readiness</h2>
              <p className="text-xs text-muted-foreground mt-1">Current GenAI semantic-convention spans; content capture is off by default.</p>
            </div>
            <span className={`rounded-full border px-2.5 py-1 text-xs ${status.recording_provider ? "border-emerald-500/40 text-emerald-400" : "border-amber-500/40 text-amber-400"}`}>
              {status.recording_provider ? "Recording provider configured" : "API only—no recording provider detected"}
            </span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 text-sm">
            <State label="Built-in tracer" ok={status.tracer_registered} />
            <State label="OpenTelemetry API" ok={status.otel_api_available} />
            <State label="OTLP endpoint declared" ok={status.otlp_endpoint_declared} empty="Not declared" />
            <State label="Prompt/output content" ok={status.content_capture} yes="Opted in" empty="Excluded" neutral />
          </div>
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-300 flex gap-2">
            <CircleAlert className="h-4 w-4 shrink-0" />
            <span><strong>Export delivery: not checked.</strong> {status.note}</span>
          </div>
          <p className="text-[10px] text-muted-foreground font-mono break-all">Provider: {status.provider ?? "unavailable"}</p>
        </CardContent>
      </Card>

      <section className="space-y-3">
        <div>
          <h2 className="font-semibold flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" />Audit history</h2>
          <p className="text-xs text-muted-foreground mt-1">Metadata only unless governance.log_content was explicitly enabled.</p>
        </div>
        {!stats.audit_enabled ? (
          <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">Audit logging is disabled. Enable <code className="font-mono">governance.audit: true</code> to create local run evidence.</CardContent></Card>
        ) : records.length === 0 ? (
          <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">Audit is enabled, but no runs have been recorded yet.</CardContent></Card>
        ) : (
          <div className="space-y-2">
            {records.map(record => (
              <Card key={record.run_id}>
                <CardContent className="p-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold truncate">{record.artifact_id} <span className="text-muted-foreground">v{record.version}</span></p>
                    <p className="text-muted-foreground mt-0.5">{new Date(record.timestamp).toLocaleString()} · {record.provider}/{record.model}</p>
                  </div>
                  <span>{record.total_tokens.toLocaleString()} tokens</span>
                  <span>{record.latency_ms} ms</span>
                  <span>${record.cost_usd.toFixed(5)}</span>
                  <code className="text-[10px] text-muted-foreground">{record.run_id.slice(0, 12)}</code>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
        </>
      )}
    </div>
  );
}

function Metric({ icon: Icon, label, value }: { icon: typeof Activity; label: string; value: string }) {
  return <Card><CardContent className="p-4"><Icon className="h-5 w-5 text-primary mb-3" /><p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p><p className="font-bold mt-1">{value}</p></CardContent></Card>;
}

function State({ label, ok, yes = "Ready", empty = "Unavailable", neutral = false }: { label: string; ok: boolean; yes?: string; empty?: string; neutral?: boolean }) {
  const color = neutral ? "text-muted-foreground" : ok ? "text-emerald-400" : "text-amber-400";
  return <div className="flex justify-between rounded-lg border p-3"><span className="text-muted-foreground">{label}</span><span className={color}>{ok ? yes : empty}</span></div>;
}

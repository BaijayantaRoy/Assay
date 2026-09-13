"use client";

import React, { useEffect, useState } from "react";
import { Activity, BarChart3, DollarSign, FileText, ShieldCheck } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { AuditRecord, AuditStats, auditLog, auditStats } from "@/lib/v1";
import { ErrorPanel, Loading, PageHeader } from "@/components/v1/shell";

export default function AnalyticsPage() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([auditStats(), auditLog({ limit: 100 })])
      .then(([summary, log]) => {
        setStats(summary);
        setRecords(log.records);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loading label="Reading audit evidence…" />;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        icon={BarChart3}
        title="Analytics"
        subtitle="Measured run evidence from the privacy-safe, file-backed audit log."
        note={
          <>
            These figures cover only runs recorded while{" "}
            <code className="font-mono">governance.audit: true</code>. Prompt and completion
            content is excluded by default. An empty log is shown as not measured, never
            as zero usage.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      {!stats?.audit_enabled ? (
        <Card>
          <CardContent className="p-12 text-center text-muted-foreground">
            <Activity className="h-12 w-12 mx-auto mb-3 opacity-25" />
            <p className="font-medium text-foreground">Audit measurement is not enabled</p>
            <p className="text-sm mt-1">
              Add <code className="font-mono">governance.audit: true</code> to assay.yaml.
              Historical usage before that point cannot be inferred.
            </p>
          </CardContent>
        </Card>
      ) : stats.records === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-muted-foreground">
            <Activity className="h-12 w-12 mx-auto mb-3 opacity-25" />
            <p className="font-medium text-foreground">Enabled, but no runs recorded yet</p>
            <p className="text-sm mt-1">No cost, volume, or trend claim is available.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric icon={Activity} label="Recorded runs" value={String(stats.records)} />
            <Metric icon={FileText} label="Artifacts observed" value={String(stats.artifacts)} />
            <Metric icon={DollarSign} label="Measured cost" value={"$" + stats.total_cost_usd.toFixed(6)} />
            <Metric icon={ShieldCheck} label="Log integrity" value={stats.integrity?.status || "not checked"} />
          </div>

          <Card>
            <CardContent className="p-5">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-muted-foreground border-b">
                    <tr>
                      <th className="pb-2 font-medium">Time</th>
                      <th className="pb-2 font-medium">Artifact</th>
                      <th className="pb-2 font-medium">Outcome</th>
                      <th className="pb-2 font-medium">Model</th>
                      <th className="pb-2 font-medium text-right">Tokens</th>
                      <th className="pb-2 font-medium text-right">Cost</th>
                      <th className="pb-2 font-medium text-right">Latency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((record) => (
                      <tr key={record.run_id} className="border-b border-border/50">
                        <td className="py-2.5 whitespace-nowrap">{formatTime(record.timestamp)}</td>
                        <td className="py-2.5 font-mono">{record.artifact_id}</td>
                        <td className="py-2.5">{record.outcome || "not recorded"}</td>
                        <td className="py-2.5">{record.model || "not recorded"}</td>
                        <td className="py-2.5 text-right">{record.total_tokens}</td>
                        <td className="py-2.5 text-right">{"$" + record.cost_usd.toFixed(6)}</td>
                        <td className="py-2.5 text-right">{record.latency_ms} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[11px] text-muted-foreground mt-4">
                Showing the latest {records.length} of {stats.records} recorded runs ·
                retention setting {stats.retention_days} days.
              </p>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-3">
        <Icon className="h-5 w-5 text-indigo-400" />
        <div>
          <p className="text-[10px] uppercase text-muted-foreground">{label}</p>
          <p className="text-lg font-bold">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "invalid timestamp" : date.toLocaleString();
}

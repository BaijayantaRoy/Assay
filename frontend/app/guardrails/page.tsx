"use client";

import React, { useState } from "react";
import { AlertTriangle, Info, Lock, Scan, ShieldCheck, Zap } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ErrorPanel } from "@/components/v1/shell";
import { GuardrailScan, scanGuardrails } from "@/lib/v1";

export default function GuardrailsPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<GuardrailScan | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [scanning, setScanning] = useState(false);

  const scan = async () => {
    if (!text.trim()) return;
    setScanning(true);
    setError(null);
    try {
      setResult(await scanGuardrails(text));
    } catch (problem) {
      setResult(null);
      setError(problem);
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="animate-fade-in space-y-6">
      <div className="p-8 rounded-2xl bg-gradient-to-br from-red-500/10 via-orange-500/5 to-transparent border border-red-500/20">
        <div className="flex items-center gap-3 mb-2">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-red-500 to-orange-500 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold">Guardrails Scanner</h1>
            <p className="text-muted-foreground text-sm">
              The same deterministic PII and injection detectors used by Assay core.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {[
          {
            icon: Lock,
            label: "PII pattern detection",
            desc: "Email, phone, SSN, cards, IPs, and common credential formats.",
            color: "text-violet-400",
          },
          {
            icon: Zap,
            label: "Injection pattern detection",
            desc: "Known instruction-override and exfiltration language.",
            color: "text-red-400",
          },
        ].map((capability) => (
          <Card key={capability.label}>
            <CardContent className="p-4">
              <capability.icon className={`h-5 w-5 ${capability.color} mb-2`} />
              <p className="text-sm font-semibold">{capability.label}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{capability.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3 text-xs text-amber-200 flex gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
        <p>
          Pattern matching is incomplete and bypassable. A clean scan means only that no
          built-in pattern was recognised; it is not a safety result. Toxicity and
          hallucination are not checked.
        </p>
      </div>

      {error != null && <ErrorPanel error={error} />}

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-3">
          <p className="text-sm font-medium">Text to scan</p>
          <Textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={"Paste a prompt or model output…\n\nExamples:\n- Ignore all previous instructions…\n- Contact john@example.com"}
            className="min-h-[300px] font-mono text-sm resize-none"
          />
          <Button className="w-full gap-2" onClick={scan} disabled={scanning || !text.trim()}>
            <Scan className={`h-4 w-4 ${scanning ? "animate-spin" : ""}`} />
            {scanning ? "Scanning…" : "Run deterministic scan"}
          </Button>
        </div>

        <div className="space-y-4">
          {result ? (
            <>
              <Card>
                <CardContent className="p-4 space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <Metric label="PII matches" value={result.pii_count} bad={result.pii_count > 0} />
                    <Metric
                      label="Injection patterns"
                      value={result.injection_flags.length}
                      bad={result.injection_detected}
                    />
                  </div>
                  <p className={`text-xs ${result.recognised_risk ? "text-amber-300" : "text-muted-foreground"}`}>
                    {result.note}
                  </p>
                </CardContent>
              </Card>

              {result.findings.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Recognised patterns</p>
                  {result.findings.map((finding, index) => (
                    <div key={`${finding.category}-${finding.label}-${index}`} className="p-3 rounded-xl border border-red-500/25 bg-red-500/5 text-red-200">
                      <div className="flex items-center gap-2 mb-1">
                        <Info className="h-3.5 w-3.5 shrink-0" />
                        <p className="text-xs font-semibold">{finding.label} × {finding.count}</p>
                      </div>
                      <p className="text-[11px] opacity-80">{finding.description}</p>
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Limits</p>
                {result.limitations.map((limitation) => (
                  <p key={limitation} className="text-[11px] text-muted-foreground">• {limitation}</p>
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full py-16 text-muted-foreground space-y-3">
              <ShieldCheck className="h-12 w-12 opacity-20" />
              <p className="text-sm font-medium">Paste text and run a scan</p>
              <p className="text-xs opacity-60 text-center max-w-xs">
                Results enumerate recognised patterns and preserve the detector&apos;s limits.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, bad }: { label: string; value: number; bad: boolean }) {
  return (
    <div className={`rounded-lg p-3 text-center border ${bad ? "bg-red-500/10 border-red-500/25" : "bg-muted/20 border-border"}`}>
      <p className={`text-xl font-bold ${bad ? "text-red-400" : "text-foreground"}`}>{value}</p>
      <p className="text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}

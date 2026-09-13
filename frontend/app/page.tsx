"use client";

/**
 * Dashboard — what is in this workspace, and what can actually be trusted.
 *
 * The previous version showed four counters from the legacy database: projects, prompts,
 * versions, evaluations. It had no idea harnesses, loops, memory, red-teaming,
 * calibration, governance or the token economy existed, so the first screen of the
 * product described a version of it that stopped being accurate months ago.
 *
 * Three rules hold this page together.
 *
 * **An empty section is not a failing score.** Zero certified judges out of zero judges
 * is not 0% — it means nothing has been written yet. Empty sections render guidance and
 * the command to try, never a red number.
 *
 * **Nothing here spends money.** The page reads files and cached state. Opening a
 * dashboard must never launch an agent or a red-team run.
 *
 * **Every tile goes somewhere that explains it.** A number a reader cannot act on is
 * decoration.
 */

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight, Bot, Brain, CheckCircle2, Coins, FileText, Gauge, Landmark,
  MinusCircle, Puzzle, RefreshCw, Swords, Terminal, TriangleAlert, Sparkles,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorPanel, Loading, pct } from "@/components/v1/shell";
import { SectionStatus, WorkspaceHealth, workspaceHealth } from "@/lib/v1";

export default function Dashboard() {
  const [health, setHealth] = useState<WorkspaceHealth | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    workspaceHealth().then(setHealth).catch(setError).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    workspaceHealth()
      .then(setHealth)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <DashboardState><Loading label="Reading the workspace…" /></DashboardState>;
  if (error != null) return <DashboardState><ErrorPanel error={error} /></DashboardState>;
  if (!health) return <DashboardState><p className="text-sm text-muted-foreground">Workspace state is unavailable.</p></DashboardState>;

  return (
    <div className="animate-fade-in space-y-6">
      <Header health={health} onRefresh={load} />
      {health.is_new ? <FirstSteps /> : <HealthGrid health={health} />}
    </div>
  );
}

function DashboardState({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">Workspace assurance overview</p>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------

function Header({ health, onRefresh }: { health: WorkspaceHealth; onRefresh: () => void }) {
  const attention = health.needs_attention.length;
  return (
    <div className="p-8 rounded-2xl bg-gradient-to-br from-violet-500/10 via-blue-500/5 to-transparent border border-violet-500/20">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{health.workspace.name}</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {health.inventory.total} artifact{health.inventory.total === 1 ? "" : "s"}
            {health.workspace.default_model && (
              <>
                {" "}· default model{" "}
                <code className="font-mono text-xs">{health.workspace.default_model}</code>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {attention > 0 ? (
            <Badge variant="outline" className="text-amber-400 border-amber-500/40 gap-1">
              <TriangleAlert className="h-3 w-3" />
              {attention} need{attention === 1 ? "s" : ""} attention
            </Badge>
          ) : !health.is_new ? (
            <Badge variant="outline" className="text-emerald-400 border-emerald-500/40 gap-1">
              <CheckCircle2 className="h-3 w-3" />
              nothing flagged
            </Badge>
          ) : null}
          <Button variant="outline" size="sm" onClick={onRefresh} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// A workspace with nothing in it needs teaching, not metrics.
// ---------------------------------------------------------------------------

const STEPS = [
  {
    icon: Sparkles,
    title: "Install a starter pack",
    body: "Ready-made prompts, harnesses and loops with eval cases already attached — the fastest way to see what a PromptFile looks like.",
    href: "/library",
    cta: "Browse the library",
  },
  {
    icon: FileText,
    title: "Write your first prompt",
    body: "One file: YAML frontmatter plus a markdown body. It carries the template, the model binding, the guardrails and its own test cases.",
    href: "/studio",
    cta: "Open the studio",
    command: "assay new support/refund-triage",
  },
  {
    icon: Bot,
    title: "Turn it into an agent",
    body: "A harness adds tools, a budget, memory and control mechanisms. Every run produces a trajectory you can assert against.",
    href: "/agents/harnesses",
    cta: "See harnesses",
    command: "assay new my/agent --kind harness",
  },
  {
    icon: Terminal,
    title: "Wire it to your coding agent",
    body: "The MCP server exposes your prompts to Claude Code, Cursor, Cowork and Zed, so an agent can search, run and test them.",
    href: "/integrations",
    cta: "Open integrations",
    command: "assay mcp",
  },
];

function FirstSteps() {
  return (
    <>
      <Card className="border-violet-500/30 bg-violet-500/5">
        <CardContent className="p-6">
          <h2 className="text-lg font-semibold">
            This workspace is empty — here is the short version
          </h2>
          <p className="text-sm text-muted-foreground mt-2 max-w-3xl leading-relaxed">
            Assay keeps prompts and agents as <strong>files in your repo</strong>, each one
            carrying its own test cases. The CLI, this workbench, the REST API and the MCP
            server are four doors onto the same engine, so nothing you do here is locked
            in. Everything below works offline with no API key.
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {STEPS.map((step, i) => (
          <Card key={step.title} className="hover:border-border/80 transition-colors">
            <CardContent className="p-5 space-y-3">
              <div className="flex items-center gap-2.5">
                <span className="h-7 w-7 rounded-full bg-violet-500/15 text-violet-400 flex items-center justify-center text-xs font-semibold">
                  {i + 1}
                </span>
                <step.icon className="h-4 w-4 text-violet-400" />
                <p className="font-semibold text-sm">{step.title}</p>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{step.body}</p>
              {step.command && (
                <code className="block text-[11px] font-mono bg-muted rounded px-2 py-1.5 text-muted-foreground">
                  $ {step.command}
                </code>
              )}
              <Link
                href={step.href}
                className="inline-flex items-center gap-1 text-xs text-violet-400 hover:underline"
              >
                {step.cta} <ArrowRight className="h-3 w-3" />
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------

function HealthGrid({ health }: { health: WorkspaceHealth }) {
  const { inventory, coverage, calibration, security, economy, spend, plugins } = health;

  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile
          icon={FileText}
          label="Artifacts"
          value={inventory.total}
          hint={Object.entries(inventory.kinds).map(([k, n]) => `${n} ${k}`).join(" · ")}
          href="/prompts"
          status="ok"
        />
        <Tile
          icon={Bot}
          label="Harnesses"
          value={inventory.kinds.harness ?? 0}
          hint="agent loops with tools and budgets"
          href="/agents/harnesses"
          status={inventory.kinds.harness ? "ok" : "empty"}
          emptyHint="none yet — assay new x --kind harness"
        />
        <Tile
          icon={RefreshCw}
          label="Loops"
          value={inventory.kinds.loop ?? 0}
          hint="verified multi-step pipelines"
          href="/agents/loops"
          status={inventory.kinds.loop ? "ok" : "empty"}
          emptyHint="none yet"
        />
        <Tile
          icon={Coins}
          label="Context saving"
          value={economy.saving_ratio != null ? pct(economy.saving_ratio, 0) : "—"}
          hint={`${economy.index_tokens.toLocaleString()} of ${economy.full_tokens.toLocaleString()} tokens`}
          href="/context/tokens"
          status={economy.over_budget ? "attention" : "ok"}
        />
      </div>

      <div>
        <h2 className="text-sm font-semibold mb-3">What can be trusted</h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Panel
            icon={CheckCircle2}
            title="Test coverage"
            status={coverage.status}
            href="/datasets"
            emptyBody="No artifacts to test yet."
            attentionBody={
              <>
                <strong>{coverage.total - coverage.tested}</strong> of {coverage.total}{" "}
                artifacts carry no eval cases, so nothing checks them. An untested artifact
                passes every run by default, which is not the same as working.
              </>
            }
            okBody={<>All {coverage.total} artifacts carry eval cases.</>}
            metric={coverage.ratio != null ? pct(coverage.ratio, 0) : "—"}
            detail={coverage.untested.slice(0, 4)}
          />

          <Panel
            icon={Gauge}
            title="Judge calibration"
            status={calibration.status}
            href="/quality/calibration"
            emptyBody={calibration.note}
            attentionBody={
              <>
                <strong>{calibration.uncertified_in_use}</strong> artifact
                {calibration.uncertified_in_use === 1 ? " uses" : "s use"} an LLM judge that
                has not passed the two-stage gate. Scores from an uncalibrated judge are
                not evidence.
              </>
            }
            okBody={<>{calibration.certified} judge(s) certified and in date.</>}
            metric={
              calibration.judges.length
                ? `${calibration.certified}/${calibration.judges.length}`
                : "—"
            }
          />

          <Panel
            icon={Swords}
            title="Injection defence"
            status={security.status}
            href="/security/redteam"
            emptyBody={security.note || "No red-team run recorded."}
            attentionBody={security.note || "The last run flagged something."}
            okBody={
              <>
                The last run defended every attack
                {security.mode === "scripted" && (
                  <>
                    {" "}— though it was a <strong>scripted</strong> run, which measures the
                    defences rather than model susceptibility
                  </>
                )}
                .
              </>
            }
            metric={
              security.attack_success_rate != null
                ? pct(security.attack_success_rate, 0)
                : security.status === "empty"
                  ? "—"
                  : "withheld"
            }
          />
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold mb-3">Operations</h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Panel
            icon={Landmark}
            title="Run log and spend"
            status={spend.status}
            href="/governance"
            emptyBody={spend.note || "No runs recorded."}
            attentionBody={spend.note || ""}
            okBody={
              <>
                {spend.records.toLocaleString()} runs recorded
                {spend.newest && (
                  <> · newest {new Date(spend.newest).toLocaleDateString()}</>
                )}
              </>
            }
            metric={spend.records ? `$${spend.total_cost_usd.toFixed(2)}` : "—"}
          />

          <Panel
            icon={Puzzle}
            title="Plugins"
            status={plugins.status}
            href="/spec"
            emptyBody="No plugins registered."
            attentionBody={
              <>
                <strong>{plugins.failures.length}</strong> plugin(s) failed to load. A
                failed plugin is shown rather than omitted — otherwise a broken install
                looks like a smaller one.
              </>
            }
            okBody={
              <>
                {plugins.total} across {Object.keys(plugins.groups).length} extension
                points.
              </>
            }
            metric={plugins.total}
            detail={plugins.failures.map((f) => `${f.name}: ${f.error}`).slice(0, 3)}
          />

          <Panel
            icon={Brain}
            title="Files that parse"
            status={inventory.unreadable.length ? "attention" : "ok"}
            href="/prompts"
            emptyBody=""
            attentionBody={
              <>
                <strong>{inventory.unreadable.length}</strong> file(s) do not parse against
                the spec, so no surface can see them.
              </>
            }
            okBody={<>Every file in this workspace parses against the spec.</>}
            metric={inventory.unreadable.length ? inventory.unreadable.length : "all"}
            detail={inventory.unreadable.map((u) => `${u.id}: ${u.error}`).slice(0, 3)}
          />
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------

function Tile({
  icon: Icon, label, value, hint, href, status, emptyHint,
}: {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  hint: string;
  href: string;
  status: SectionStatus;
  emptyHint?: string;
}) {
  return (
    <Link href={href}>
      <Card className="h-full hover:border-violet-500/40 transition-colors cursor-pointer">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-1">
            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
              {label}
            </p>
          </div>
          <p className={`text-2xl font-bold ${status === "empty" ? "text-muted-foreground/50" : ""}`}>
            {value}
          </p>
          <p className="text-[11px] text-muted-foreground mt-1 leading-snug">
            {status === "empty" && emptyHint ? emptyHint : hint}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}

const PANEL_TONE: Record<
  SectionStatus,
  { border: string; icon: string; Icon: React.ElementType }
> = {
  ok: { border: "border-border", icon: "text-emerald-400", Icon: CheckCircle2 },
  attention: { border: "border-amber-500/40", icon: "text-amber-400", Icon: TriangleAlert },
  empty: {
    border: "border-dashed border-border",
    icon: "text-muted-foreground/50",
    Icon: MinusCircle,
  },
};

function Panel({
  icon: Icon, title, status, href, emptyBody, attentionBody, okBody, metric, detail,
}: {
  icon: React.ElementType;
  title: string;
  status: SectionStatus;
  href: string;
  emptyBody: React.ReactNode;
  attentionBody: React.ReactNode;
  okBody: React.ReactNode;
  metric: React.ReactNode;
  detail?: string[];
}) {
  const tone = PANEL_TONE[status];
  const body = status === "empty" ? emptyBody : status === "attention" ? attentionBody : okBody;

  return (
    <Card className={tone.border}>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-muted-foreground" />
            <p className="text-sm font-semibold">{title}</p>
          </div>
          <div className="flex items-center gap-1.5">
            <tone.Icon className={`h-3.5 w-3.5 ${tone.icon}`} />
            <span
              className={`text-sm font-mono font-semibold ${
                status === "empty" ? "text-muted-foreground/50" : ""
              }`}
            >
              {metric}
            </span>
          </div>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">{body}</p>

        {detail && detail.length > 0 && status === "attention" && (
          <ul className="space-y-0.5">
            {detail.map((d) => (
              <li key={d} className="text-[10px] font-mono text-muted-foreground truncate">
                · {d}
              </li>
            ))}
          </ul>
        )}

        <Link
          href={href}
          className="inline-flex items-center gap-1 text-[11px] text-violet-400 hover:underline"
        >
          {status === "empty" ? "Learn what this is" : "Open"}{" "}
          <ArrowRight className="h-3 w-3" />
        </Link>
      </CardContent>
    </Card>
  );
}

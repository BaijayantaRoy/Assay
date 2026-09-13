"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  BookOpen,
  CheckCircle2,
  FileText,
  HelpCircle,
  Map as MapIcon,
  Menu,
  Palette,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/v1/shell";
import { PAGE_GUIDES, type PageGuide } from "@/components/v1/guide";

type GuideArea = "workspace" | "create" | "evidence" | "agents" | "assurance" | "operations";

const AREAS: { id: "all" | GuideArea; label: string }[] = [
  { id: "all", label: "All guides" },
  { id: "workspace", label: "Workspace" },
  { id: "create", label: "Create" },
  { id: "evidence", label: "Evaluate" },
  { id: "agents", label: "Agents" },
  { id: "assurance", label: "Assurance" },
  { id: "operations", label: "Operations" },
];

const AREA_LABELS: Record<GuideArea, string> = {
  workspace: "Workspace",
  create: "Create",
  evidence: "Evaluate",
  agents: "Agents",
  assurance: "Assurance",
  operations: "Operations",
};

const GUIDE_AREAS: Record<string, GuideArea> = {
  "/": "workspace",
  "/projects": "workspace",
  "/projects/": "workspace",
  "/prompts": "workspace",
  "/prompts/": "workspace",
  "/library": "create",
  "/studio": "create",
  "/compare": "evidence",
  "/abtests": "evidence",
  "/guardrails": "evidence",
  "/datasets": "evidence",
  "/chains": "agents",
  "/agents/harnesses": "agents",
  "/agents/loops": "agents",
  "/agents/memory": "agents",
  "/context/tokens": "agents",
  "/security/redteam": "assurance",
  "/quality/calibration": "assurance",
  "/governance": "assurance",
  "/benchmark": "assurance",
  "/integrations": "operations",
  "/analytics": "operations",
  "/observability": "operations",
  "/spec": "operations",
  "/settings/models": "operations",
  "/settings": "operations",
  "/delivery": "operations",
  "/help": "operations",
};

const START_HERE = [
  {
    title: "I need a tested starting point",
    detail: "Browse installable PromptFiles that carry their own declared eval scope.",
    href: "/library",
    label: "Open Starter Library",
    Icon: Sparkles,
  },
  {
    title: "I already have a prompt",
    detail: "Find the file in the workspace, then render it or inspect its existing evals.",
    href: "/prompts",
    label: "Open All Prompts",
    Icon: FileText,
  },
  {
    title: "I need a new draft",
    detail: "Use the visual builder to create a new body-only draft, then add its source metadata and evals.",
    href: "/studio",
    label: "Open Prompt Studio",
    Icon: FileText,
  },
  {
    title: "I am building an agent",
    detail: "Start with a file-declared harness and use its trajectory as the record of what happened.",
    href: "/agents/harnesses",
    label: "Open Harnesses",
    Icon: Bot,
  },
] as const;

const AGENT_LIFECYCLE = [
  {
    title: "Declare the harness",
    detail: "Name the allowed tools, budget, memory, and controls in the artifact.",
    href: "/agents/harnesses",
    Icon: Bot,
  },
  {
    title: "Run and inspect",
    detail: "Read the trajectory and tool calls, not only the final answer.",
    href: "/agents/harnesses",
    Icon: Search,
  },
  {
    title: "Verify the path",
    detail: "Add trajectory assertions and test them so an unsafe route can fail.",
    href: "/agents/harnesses",
    Icon: CheckCircle2,
  },
  {
    title: "Extend with evidence",
    detail: "Use Loops for verified handoffs, then use Red Team before relying on risky behavior.",
    href: "/agents/loops",
    Icon: ShieldCheck,
  },
] as const;

const PROMPT_LIFECYCLE = [
  {
    title: "Start or draft",
    detail: "Install a tested starter or save a new body-only draft.",
    href: "/library",
  },
  {
    title: "Inspect and change",
    detail: "Find the PromptFile, edit its body, and confirm the new version.",
    href: "/prompts",
  },
  {
    title: "Prove it",
    detail: "Declare evals in the source file, then run the existing cases in Eval Lab.",
    href: "/datasets",
  },
  {
    title: "Compare safely",
    detail: "Use a shared case set and inspect the interval before choosing a variant or model.",
    href: "/compare",
  },
  {
    title: "Put it to work",
    detail: "Generate coding-agent instructions, copy MCP config, or export rendered text.",
    href: "/integrations",
  },
] as const;

const GLOBAL_CONTROLS = [
  {
    title: "Sidebar menus",
    detail: "The left navigation groups pages by workflow. On a phone, use the menu button; Collapse changes only the sidebar width.",
    Icon: Menu,
  },
  {
    title: "Portal map",
    detail: "The top-bar map shows how PromptFiles move from writing through proof, agent work, trust, distribution, and operations.",
    Icon: MapIcon,
  },
  {
    title: "About this page",
    detail: "The top-bar question mark opens the complete page guide: prerequisites, effects, exact steps, limits, and linked next pages.",
    Icon: HelpCircle,
  },
  {
    title: "Theme and API root",
    detail: "The sidebar footer cycles light, dark, and eye-care themes. API root opens the stable REST surface in a separate tab.",
    Icon: Palette,
  },
] as const;

function searchText(guide: PageGuide) {
  return [guide.title, guide.subtitle, guide.what, ...guide.flow].join(" ").toLowerCase();
}

export default function HelpPage() {
  const [query, setQuery] = useState("");
  const [area, setArea] = useState<"all" | GuideArea>("all");
  const guides = useMemo(
    () => Object.entries(PAGE_GUIDES)
      .map(([href, guide]) => ({ href, guide, area: GUIDE_AREAS[href] || "operations" }))
      .sort((left, right) => left.guide.title.localeCompare(right.guide.title)),
    [],
  );
  const visibleGuides = useMemo(() => {
    const term = query.trim().toLowerCase();
    return guides.filter((entry) => (
      (area === "all" || entry.area === area) &&
      (!term || searchText(entry.guide).includes(term))
    ));
  }, [area, guides, query]);

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={HelpCircle}
        title="Help Centre"
        subtitle="A connected, page-by-page guide to the Assay workbench."
        gradient="from-violet-500/10 via-blue-500/5"
        iconGradient="from-violet-500 to-blue-500"
        border="border-violet-500/20"
        note={
          <>
            Start with the outcome you need, then open the relevant page. Each guide below
            is drawn from the same page-level instructions available throughout the portal —
            it describes what the page actually shows and what a successful next step looks like.
          </>
        }
      />

      <section aria-labelledby="start-here-heading" className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <Card className="border-violet-500/25 bg-violet-500/[0.04]">
          <CardContent className="p-5">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-violet-500/15 text-violet-400">
                <BookOpen className="h-4 w-4" aria-hidden="true" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-violet-400">Start here</p>
                <h2 id="start-here-heading" className="mt-1 text-lg font-semibold">Choose the job you are doing</h2>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  The portal is organised by workflow, not by a hidden database model. Pick the
                  closest starting point; every page guide links to its natural next step.
                </p>
              </div>
            </div>
            <div className="mt-5 grid gap-2 sm:grid-cols-2">
              {START_HERE.map(({ title, detail, href, label, Icon }) => (
                <Link
                  key={href}
                  href={href}
                  className="group rounded-xl border bg-background/70 p-3 transition-colors hover:border-violet-500/45 hover:bg-violet-500/[0.06]"
                >
                  <Icon className="h-4 w-4 text-violet-400" aria-hidden="true" />
                  <p className="mt-2 text-xs font-semibold">{title}</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{detail}</p>
                  <span className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-violet-400 group-hover:underline">
                    {label} <ArrowRight className="h-3 w-3" aria-hidden="true" />
                  </span>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-emerald-500/25 bg-emerald-500/[0.035]">
          <CardContent className="p-5">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400">
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400">Agent lifecycle</p>
                <h2 className="mt-1 text-lg font-semibold">Move from a declared agent to evidence</h2>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  A correct-looking answer is not enough. The lifecycle keeps the permitted
                  path, its verification, and any higher-risk testing visible.
                </p>
              </div>
            </div>
            <ol className="mt-5 grid gap-2 sm:grid-cols-2" aria-label="Agent lifecycle steps">
              {AGENT_LIFECYCLE.map(({ title, detail, href, Icon }, index) => (
                <li key={title}>
                  <Link
                    href={href}
                    className="group flex h-full gap-3 rounded-xl border bg-background/70 p-3 transition-colors hover:border-emerald-500/45 hover:bg-emerald-500/[0.06]"
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-emerald-500/35 bg-emerald-500/10 text-[10px] font-bold text-emerald-400">
                      {index + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 text-xs font-semibold">
                        <Icon className="h-3.5 w-3.5 text-emerald-400" aria-hidden="true" />
                        {title}
                      </span>
                      <span className="mt-1 block text-[11px] leading-relaxed text-muted-foreground">{detail}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="prompt-lifecycle-heading">
        <Card className="border-blue-500/25 bg-blue-500/[0.035]">
          <CardContent className="p-5 sm:p-6">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-500/15 text-blue-400">
                <FileText className="h-4 w-4" aria-hidden="true" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-blue-400">Prompt lifecycle</p>
                <h2 id="prompt-lifecycle-heading" className="mt-1 text-lg font-semibold">From an idea to a usable, evidenced prompt</h2>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  This is the normal connected path. Where the portal does not yet author a source field,
                  the step says so instead of pretending the control exists.
                </p>
              </div>
            </div>
            <ol className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-5" aria-label="Prompt lifecycle steps">
              {PROMPT_LIFECYCLE.map(({ title, detail, href }, index) => (
                <li key={title}>
                  <Link
                    href={href}
                    className="group flex h-full gap-3 rounded-xl border bg-background/70 p-3 transition-colors hover:border-blue-500/45 hover:bg-blue-500/[0.06]"
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-blue-500/35 bg-blue-500/[0.08] text-[10px] font-bold text-blue-400">
                      {index + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="text-xs font-semibold">{title}</span>
                      <span className="mt-1 block text-[11px] leading-relaxed text-muted-foreground">{detail}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="global-controls-heading">
        <Card className="border-dashed">
          <CardContent className="p-5 sm:p-6">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">Getting around</p>
              <h2 id="global-controls-heading" className="mt-1 text-lg font-semibold">The controls that are available everywhere</h2>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {GLOBAL_CONTROLS.map(({ title, detail, Icon }) => (
                <div key={title} className="rounded-xl border bg-muted/[0.12] p-4">
                  <Icon className="h-4 w-4 text-violet-400" aria-hidden="true" />
                  <p className="mt-2 text-xs font-semibold">{title}</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{detail}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="guide-directory-heading" className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-blue-400">Guide directory</p>
            <h2 id="guide-directory-heading" className="mt-1 text-xl font-semibold">Every guided page in one place</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Search titles, subtitles, what a page does, or the steps it asks you to take.
            </p>
          </div>
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {visibleGuides.length} of {guides.length} guides shown
          </p>
        </div>

        <div className="rounded-2xl border bg-card p-3 sm:p-4">
          <label className="relative block">
            <span className="sr-only">Search page guides</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search titles, subtitles, what a page does, or its steps…"
              className="pl-9"
            />
          </label>
          <div className="mt-3 flex flex-wrap gap-2" aria-label="Filter page guides by workflow">
            {AREAS.map((filter) => {
              const active = area === filter.id;
              return (
                <button
                  key={filter.id}
                  type="button"
                  onClick={() => setArea(filter.id)}
                  aria-pressed={active}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                    active
                      ? "border-blue-500/35 bg-blue-500/10 text-blue-400"
                      : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
                  }`}
                >
                  {filter.label}
                </button>
              );
            })}
          </div>
        </div>

        {visibleGuides.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="p-10 text-center">
              <Search className="mx-auto h-8 w-8 text-muted-foreground/45" aria-hidden="true" />
              <p className="mt-3 text-sm font-semibold">No page guides match that search</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Try a page name, an outcome such as “model” or “audit,” or clear the workflow filter.
              </p>
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setArea("all");
                }}
                className="mt-4 text-xs font-semibold text-blue-400 hover:underline"
              >
                Show every guide
              </button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {visibleGuides.map(({ href, guide, area: guideArea }) => (
              <GuideCard key={href} href={href} guide={guide} area={guideArea} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function GuideCard({
  href,
  guide,
  area,
}: {
  href: string;
  guide: PageGuide;
  area: GuideArea;
}) {
  const steps = guide.flow.slice(0, 3);
  const isContextualGuide = href.endsWith("/");

  return (
    <Card className="overflow-hidden border-border/80">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Badge variant="outline" className="border-blue-500/30 bg-blue-500/[0.06] text-[10px] text-blue-400">
              {AREA_LABELS[area]}
            </Badge>
            <h3 className="mt-2 text-lg font-semibold leading-tight">{guide.title}</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{guide.subtitle}</p>
            {isContextualGuide && (
              <p className="mt-2 text-[11px] font-medium text-blue-400">
                Open a specific item from its list to use this guide in context.
              </p>
            )}
          </div>
          {isContextualGuide ? (
            <span
              title="Open an item from its list to see this guide in context"
              aria-label={`Open an item from its list to see ${guide.title}`}
              className="shrink-0 rounded-lg border border-dashed bg-muted/20 p-2 text-muted-foreground"
            >
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </span>
          ) : (
            <Link
              href={href}
              aria-label={`Open ${guide.title}`}
              className="shrink-0 rounded-lg border bg-background p-2 text-muted-foreground transition-colors hover:border-blue-500/40 hover:text-blue-400"
            >
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          )}
        </div>

        <div className="mt-4 border-t pt-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">What it does</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{guide.what}</p>
        </div>

        <div className="mt-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">Quick steps</p>
          <ol className="mt-2 space-y-2">
            {steps.map((step, index) => (
              <li key={step} className="flex gap-2.5 text-xs leading-relaxed">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-blue-500/35 bg-blue-500/[0.08] text-[10px] font-bold text-blue-400">
                  {index + 1}
                </span>
                <span className="pt-0.5">{step}</span>
              </li>
            ))}
          </ol>
        </div>

        {guide.related && guide.related.length > 0 && (
          <div className="mt-4 border-t pt-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">Related pages</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {guide.related.map((related) => (
                <Link
                  key={related.href}
                  href={related.href}
                  className="rounded-lg border bg-muted/25 px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:border-violet-500/35 hover:text-violet-300"
                >
                  {related.label} <span aria-hidden="true">→</span>
                </Link>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.045] p-3 text-[11px] leading-relaxed text-muted-foreground">
          <strong className="text-emerald-400">Need the complete guide?</strong> Open {guide.title},
          then use <strong>About this page</strong> in the top-right corner for the full flow,
          why the page exists, and the expected result.
        </div>
      </CardContent>
    </Card>
  );
}

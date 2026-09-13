"use client";

/**
 * The portal-wide map, and a "?" for every single page — the two things this workbench was
 * missing. Both were requested explicitly after a demo of another project's inline guide:
 * a persistent way to see how the whole thing connects, and a persistent way to ask "what
 * is this page, why does it exist, how do I use it" without hunting for docs.
 *
 * Two components, one registry:
 *
 * - `PAGE_GUIDES` is the map from every route in `sidebar.tsx` to its why/what/how/expect.
 *   Missing an entry here is a bug, not a fallback case — `TopBar` renders "no guide yet"
 *   loudly rather than silently, on the theory that a visible gap gets fixed and an invisible
 *   one does not.
 * - `LAYERS` is the portal-wide architecture: what stage each page belongs to, in the order
 *   a prompt actually moves through the workbench, from first draft to production evidence.
 *
 * Both render through the same `Sheet` shell so the "?" and the map feel like one system,
 * not two features bolted on at different times.
 */

import React, { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowDown, HelpCircle, Map as MapIcon, X, ChevronDown,
} from "lucide-react";

// ---------------------------------------------------------------------------
// shared modal shell
// ---------------------------------------------------------------------------

function Sheet({
  eyebrow,
  title,
  subtitle,
  onClose,
  children,
  footer,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const titleId = useId();
  const subtitleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
        'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((element) => element.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={subtitleId}
        className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border bg-card shadow-2xl"
      >
        <div className="shrink-0 border-b bg-gradient-to-br from-violet-500/10 via-blue-500/5 to-transparent p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-widest text-violet-400">
                {eyebrow}
              </p>
              <h2 id={titleId} className="mt-1 text-2xl font-bold">{title}</h2>
              <p id={subtitleId} className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
            </div>
            <button
              ref={closeRef}
              onClick={onClose}
              className="shrink-0 rounded-full border bg-background p-2 text-muted-foreground hover:text-foreground"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-muted/20 p-6">{children}</div>

        {footer && (
          <div className="shrink-0 border-t bg-card p-5">{footer}</div>
        )}
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">
        {label}
      </p>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// per-page guide
// ---------------------------------------------------------------------------

export type PageGuide = {
  title: string;
  subtitle: string;
  /** The failure or gap this page exists to close. Not "what it does" — why it needed to exist. */
  why: string;
  /** What is actually on screen, in plain terms. */
  what: string;
  /** The flow a first-time visitor should follow, in order. 3–5 steps. */
  flow: string[];
  /** What "this worked" looks like when the flow is followed. */
  expect: string;
  /** The consequences of using this surface. These prevent a helpful-looking guide from hiding a write or run. */
  effects?: string[];
  /** What has to exist or be configured before the primary flow can work. */
  prerequisites?: string[];
  /** Important things a visitor cannot do from this screen today. */
  limits?: string[];
  related?: { label: string; href: string }[];
};

export const PAGE_GUIDES: Record<string, PageGuide> = {
  "/": {
    title: "Dashboard",
    subtitle: "The truthful launch point — not a vanity scoreboard.",
    why:
      "A dashboard that shows green when nothing has been tried yet is lying by omission. " +
      "This one distinguishes 'nothing here yet' from 'this is broken,' because those two " +
      "states call for opposite reactions and most dashboards conflate them into one red number.",
    what:
      "Workspace health across every trust layer — coverage, calibration, security, spend, " +
      "plugins — each carrying its own status of ok, attention, or empty. A brand-new " +
      "workspace gets a first-steps view instead of a grid of zeros.",
    flow: [
      "Read the top row first — it says what actually exists, not what is wrong.",
      "Anything marked \"attention\" has a reason attached; open it to see the gap.",
      "\"Empty\" sections are not failures — they mean that layer has not been used yet.",
      "Open the tile for the one gap you want to address; every tile leads to the matching workspace.",
    ],
    expect: "You know, in under a minute, what is proven, what is unproven, and what to do next.",
    effects: ["Read-only workspace health", "Refresh reads again; it does not run an artifact"],
    related: [
      { label: "Starter Library", href: "/library" },
      { label: "Governance", href: "/governance" },
    ],
  },
  "/projects": {
    title: "Projects",
    subtitle: "Namespaces, derived from prompt ids — not a database entity.",
    why:
      "A workspace with fifty prompts and no grouping makes 'which of these is the refund " +
      "one' a search problem. There used to be a separate `Project` database row for this; " +
      "now the grouping comes straight from the id, so it cannot drift out of sync with " +
      "what is actually in `/v1/prompts` the way a second, hand-maintained table could.",
    what:
      "Every prompt id's first path segment (`billing` in `billing/dunning-email`), grouped " +
      "into cards with a count. Ids with no slash land in a single \"(none)\" bucket.",
    flow: [
      "Give a new prompt an id with the namespace you want as its prefix — that alone creates the group.",
      "Open a namespace to see every prompt under it.",
      "Use All Prompts instead if you want to filter across namespaces at once.",
    ],
    expect: "A namespace list that always matches reality, because it is read from the same ids the CLI sees.",
    effects: ["Read-only namespace grouping derived from PromptFile ids"],
    related: [{ label: "All Prompts", href: "/prompts" }],
  },
  "/projects/": {
    title: "Project detail",
    subtitle: "A filtered namespace view — not a separate project record.",
    why:
      "A namespace needs enough room to find the right artifact without inventing a second project store that can drift from the files.",
    what:
      "The prompts whose ids begin with this namespace, plus a local filter. Opening an item takes you to the body editor, render form, eval runner, and history for that PromptFile.",
    flow: [
      "Use the filter to narrow the namespace by prompt id, name, or description.",
      "Open the PromptFile you want to inspect or change.",
      "To add another item here, create a new draft with the same `namespace/...` id in Prompt Studio or create the PromptFile in `prompts/`.",
    ],
    expect: "The namespace stays in sync with the PromptFile ids on disk, without a separate project to maintain.",
    effects: ["Read-only local filter", "No project metadata is created or changed here"],
    related: [{ label: "All Prompts", href: "/prompts" }, { label: "Prompt Studio", href: "/studio" }],
  },
  "/prompts": {
    title: "All Prompts",
    subtitle: "Every PromptFile in this workspace — the same list `assay ls` sees.",
    why:
      "This used to read the legacy 0.x database — a second, disconnected catalogue from " +
      "the one the CLI, MCP server, and Starter Library actually use, so a prompt installed " +
      "from the library never showed up here. It now reads `/v1/prompts` directly, the same " +
      "file-backed store everything else in this workbench is built on.",
    what:
      "A searchable, namespace-filterable list of prompts, each opening into a detail view " +
      "with a body editor, metadata summary, render-only form, eval results, and version history.",
    flow: [
      "Filter by namespace or search by id, name, description, or tag.",
      "Open one to read its body, render it against variables, or run its eval cases.",
      "Prefer the Starter Library or Prompt Studio for anything new — this is where existing work lives, not where new work starts.",
    ],
    expect: "Every prompt on disk shows up here, and nothing shows up here that is not really on disk.",
    effects: ["Read-only list and filters"],
    related: [{ label: "Starter Library", href: "/library" }, { label: "Prompt Studio", href: "/studio" }],
  },
  "/prompts/": {
    title: "Prompt detail",
    subtitle: "Edit the body, render safely, run declared evals, and inspect the version trail.",
    why:
      "A PromptFile needs a focused work surface where a small body change can be rendered and checked without pretending that a preview was a model run.",
    what:
      "A metadata summary, body-only editor, no-model render form, runner for evals already declared in the file, and version history. Saving the body creates a new version.",
    flow: [
      "Read the current status, model, tags, and version before changing the body.",
      "Edit the Body and select Save; confirm the version number advances before treating the change as persisted.",
      "Fill any variables and select Render to inspect the assembled prompt without making a model call.",
      "If evals are already declared, run them here or use Eval Lab for an optional model override and the full report.",
      "Edit frontmatter, guardrails, and eval cases directly in the PromptFile under `prompts/` (then run `assay lint` and `assay test`) until a dedicated editor is available.",
    ],
    expect: "A versioned body change and either an eval result or an explicit indication that no evals are declared yet.",
    effects: ["Save writes a new PromptFile version", "Render makes no model call", "Run evals may invoke the bound model and incur its normal cost"],
    limits: ["This screen does not edit frontmatter, guardrails, or eval definitions.", "It shows the editable body and metadata summary, not a raw-file editor."],
    related: [{ label: "Eval Lab", href: "/datasets" }, { label: "A/B Testing", href: "/abtests" }, { label: "Guardrails", href: "/guardrails" }],
  },
  "/library": {
    title: "Starter Library",
    subtitle: "Real, tested PromptFiles you can install with one click.",
    why:
      "A brand-new workspace has nothing in it, and 'write your first prompt from a blank " +
      "page' is a bad first five minutes. Every starter here is a genuine PromptFile — " +
      "validated against the spec, carrying its own eval case — not a demo that only looks real.",
    what: "A browsable, filterable, searchable catalogue of installable prompts, grouped by category.",
    flow: [
      "Filter by category or search for what you need.",
      "Select one or several starters.",
      "Install — this copies the file into your prompts directory unchanged; nothing already there is overwritten.",
      "Open it afterward in All Prompts, or use `assay show <id>`, to inspect the exact PromptFile that was installed.",
    ],
    expect: "A working, tested prompt on disk in your own `prompts/` directory, ready to run or edit.",
    effects: ["Install writes PromptFiles into the workspace", "Existing artifact files are skipped rather than overwritten"],
    related: [{ label: "All Prompts", href: "/prompts" }, { label: "Eval Lab", href: "/datasets" }],
  },
  "/studio": {
    title: "Prompt Studio",
    subtitle: "Visual prompt-body builder that saves an explicit unverified draft.",
    why:
      "Editing YAML frontmatter and a Markdown body by hand works, but seeing the anatomy — " +
      "instruction blocks as distinct visual pieces makes omissions easier to spot. The " +
      "current Studio deliberately saves a draft, because model binding, guardrails and " +
      "eval authoring are not yet editable on this screen.",
    what: "A visual body builder with preview, copy, and save-to-workspace for a new draft PromptFile.",
    flow: [
      "Choose Anatomy Builder for a structured prompt body or Vibe Coding Studio for a generated coding brief.",
      "Assemble the prompt body from focused instruction blocks.",
      "Choose a canonical namespace/id and save it; the artifact is marked draft and unverified.",
      "Open the new item in All Prompts, then add frontmatter and eval cases directly in the PromptFile before using Eval Lab or `assay test <id>`.",
    ],
    expect: "A draft PromptFile on disk, honestly marked unverified until eval cases are added.",
    effects: ["Copy writes only to the clipboard", "Save creates a new draft PromptFile in the workspace"],
    limits: ["Studio does not open or edit an existing PromptFile.", "Model binding, tags, status, guardrails, and eval definitions are not editable here yet."],
    related: [{ label: "All Prompts", href: "/prompts" }, { label: "Eval Lab", href: "/datasets" }],
  },
  "/compare": {
    title: "Model Comparator",
    subtitle: "A model-comparison use case of the shared paired A/B screen.",
    why:
      "Model choice is usually guessed at or inherited from whatever the last person used. " +
      "Running the identical prompt across several models side by side turns that guess into a comparison.",
    what: "This compatibility route opens the same Paired A/B Comparison screen as A/B Testing. To compare models fairly, select the same eval-bearing PromptFile for A and B, then set different model overrides.",
    flow: [
      "Replace the screen's initial selections with the same eval-bearing PromptFile in both A and B.",
      "Set a different model override for A and B, then run the shared cases.",
      "Read the paired score delta, uncertainty interval, and measured total cost.",
    ],
    expect: "A concrete basis for a model choice, instead of an assumption carried over from a previous project.",
    effects: ["Runs paired evals and may invoke both selected models", "Results are shown for this session; the page is not a persistent experiment registry"],
    limits: ["There is not yet a separate model-only comparator interface; this is the A/B screen with a model-comparison setup."],
    related: [{ label: "Global Models", href: "/settings/models" }],
  },
  "/abtests": {
    title: "A/B Testing",
    subtitle: "Paired offline experiments on exactly the same declared eval cases.",
    why:
      "\"I changed the prompt and it feels better\" is not evidence. This exists so a variant " +
      "has to earn its promotion with a measured difference, not a hunch.",
    what: "A paired case-bootstrap comparison of two prompt or model variants, with honest winner withholding.",
    flow: [
      "Define the variants you are actually deciding between.",
      "Use the same declared cases and assertions for both variants; the API refuses mismatches.",
      "Run both variants and inspect the B-minus-A interval, exclusions, and combined cost.",
    ],
    expect: "A winner declared on a metric you chose in advance, with a sample size that supports the claim.",
    effects: ["Runs paired evals and may invoke the selected model bindings", "Results are session-local rather than a saved experiment library"],
    related: [{ label: "Judge Calibration", href: "/quality/calibration" }],
  },
  "/guardrails": {
    title: "Guardrails",
    subtitle: "Run the core deterministic PII and injection pattern detectors.",
    why:
      "A prompt that works on the happy path can still leak a phone number or repeat an " +
      "injected instruction from user content. This is the layer that checks for that " +
      "specifically, rather than trusting that a good answer means a safe one.",
    what: "A paste-only, deterministic pattern scan that enumerates recognised PII and injection language and states what was not checked. Findings are not attached to an artifact or saved.",
    flow: [
      "Paste the exact prompt text, input, or output you want to inspect.",
      "Read recognised PII and injection patterns; a clean result is not a safety claim.",
      "Change the source artifact outside this scanner, then paste the revised text and rescan.",
    ],
    expect: "A per-category finding count, not a single pass/fail that hides which risk actually showed up.",
    effects: ["Deterministic scan only", "Text and findings are transient; this page does not modify a PromptFile"],
    limits: ["There is no artifact picker, automatic output capture, or saved scan history on this screen."],
    related: [{ label: "Red Team", href: "/security/redteam" }],
  },
  "/chains": {
    title: "Verified Loops",
    subtitle: "This compatibility route now opens the first-class Loop workspace.",
    why:
      "The old chain database was a second execution model with inert editing controls. " +
      "PromptFile loops now cover sequential, concurrent, and supervised work while " +
      "preserving per-step verification evidence.",
    what: "A redirect to file-backed loops, where every handoff can carry its own verification evidence.",
    flow: [
      "Open the Loops workspace and choose a file-backed loop.",
      "Run it and inspect every step, handoff, and verification result.",
      "Add loop evals so a broken handoff fails the same assurance gate as any other artifact.",
    ],
    expect: "One multi-step execution model shared by CLI, MCP, REST, and the workbench.",
    effects: ["Compatibility redirect; use Loops for execution"],
    related: [{ label: "Loops", href: "/agents/loops" }],
  },
  "/agents/harnesses": {
    title: "Harnesses",
    subtitle: "Agents declared as files: loop, tools, budget, memory, controls.",
    why:
      "Running an agent is easy. Knowing whether it did the right thing, for the right " +
      "reason, is not. A harness produces a trajectory — the full record of what it actually " +
      "did — so an assertion can check the path taken, not only the final answer. An agent " +
      "can reach a correct result through a tool call it should never have made.",
    what: "A list of existing file-declared harnesses, each with its tools, budget, and trajectory assertions; choose one, set a goal, run it, and inspect what it actually did.",
    flow: [
      "Create or edit a harness in a PromptFile or with `assay new my/agent --kind harness`; this portal screen runs existing harnesses only.",
      "Choose a harness, state the goal, and use Dry run first when you need a read-only controller with no side effects.",
      "Run it only after reviewing its shown budget; then read the trajectory, denied calls, verification mark, cost, and stop reason—not only the final answer.",
      "Add trajectory assertions in the harness file and use `assay test <id>` to prove the allowed path.",
    ],
    expect: "A record of every tool call the agent made, and a test that would fail if it took a route it should not have.",
    effects: ["Dry run uses a read-only controller", "A normal run can call tools and invoke a model within the shown budget"],
    limits: ["This screen does not create, edit, or attach evals to a harness."],
    related: [{ label: "Loops", href: "/agents/loops" }, { label: "Red Team", href: "/security/redteam" }],
  },
  "/agents/loops": {
    title: "Loops",
    subtitle: "A verified multi-step pipeline — the outer loop around an agent.",
    why:
      "Errors compound. A 90%-accurate step feeding another 90%-accurate step does not stay " +
      "at 90%, so by step eighteen of a twenty-step chain you can have a confident, coherent, " +
      "wrong result. Verification runs at every handoff here, not only at the end — and a " +
      "loop that verified nothing reports 'not checked,' never a pass.",
    what: "Existing loop definitions with per-step verification, stall detection, and a convergence report. This screen selects and runs a loop; its definition remains file-backed.",
    flow: [
      "Author the steps and their verification in the loop PromptFile or CLI before returning here.",
      "Choose the existing loop and review it; selecting Run loop executes the declared commands in the workspace root.",
      "Read whether it converged or stalled, then inspect every cycle and handoff—stalling is reported explicitly, not just as a failure.",
      "Use `assay test <id>` to assert it converged and every step actually verified, not merely ran.",
    ],
    expect: "A pass that means every handoff was checked, or a clear 'not checked' where verification did not happen — never a false green.",
    effects: ["Run loop executes real commands in the workspace", "A run may invoke models and tools declared by the loop"],
    limits: ["This screen does not create or edit loop definitions."],
    related: [{ label: "Harnesses", href: "/agents/harnesses" }, { label: "Memory", href: "/agents/memory" }],
  },
  "/agents/memory": {
    title: "Memory",
    subtitle: "What an agent carries from one run into the next.",
    why:
      "Without memory, every run starts cold and repeats work it already did. Recall here " +
      "ranks exact identifiers — file paths, tool names — above fuzzy similarity, because " +
      "that is what agents actually search by, and no embedding model is required for it to work offline.",
    what: "A read-only overview and search of what past runs recorded, namespaced, with hybrid keyword-plus-entity ranking.",
    flow: [
      "Choose a namespace by selecting its card.",
      "Search it by an identifier you expect to recur — a file path, a tool name, or an artifact id.",
      "Read what earlier runs recorded before assuming an agent has to rediscover it.",
      "If context must be removed, use `assay memory forget --namespace <name>` in the terminal; deletion is deliberately not exposed in this portal yet.",
    ],
    expect: "A later run recalling something a past run learned, instead of rediscovering it from zero.",
    effects: ["Read-only search in the portal", "Terminal-only forget deletes a namespace—review the name before running it"],
    limits: ["There is no Forget or edit control in the portal."],
    related: [{ label: "Harnesses", href: "/agents/harnesses" }],
  },
  "/context/tokens": {
    title: "Token Economy",
    subtitle: "What an agent has to load to know what exists, versus loading everything.",
    why:
      "Context is a budget, not a bucket. Pasting every prompt body into an agent's context " +
      "spends its budget on material it did not ask for — the exact failure progressive " +
      "disclosure exists to prevent.",
    what: "A measured comparison of the compact tier-1 index versus the full workspace, for this workspace specifically.",
    flow: [
      "Measure this workspace rather than trusting a general claim about savings.",
      "Read the saving next to its denominator — a percentage without the base number to check it against is not a claim, it is a mood.",
      "Use the index-first pattern (`assay show <id>` on demand) in anything you wire into an agent.",
    ],
    expect: "A concrete token count for the index versus the full library, specific to what is actually in this workspace.",
    effects: ["Read-only workspace token measurement"],
    related: [{ label: "Integrations", href: "/integrations" }],
  },
  "/security/redteam": {
    title: "Red Team",
    subtitle: "Indirect prompt injection, run against a harness and scored.",
    why:
      "Attacks arrive through tool output — content the agent did not write and cannot vouch " +
      "for. Benign controls run alongside the attacks so a detector that flags everything " +
      "scores badly rather than perfectly. None of this is a safety guarantee: it raises the " +
      "cost of an attack, it does not close the class of vulnerability.",
    what: "A versioned attack corpus (plus benign controls) run against a chosen harness, reporting attack success rate only when the run was actually usable.",
    flow: [
      "Pick the harness to test and select Run corpus; the portal runs the full versioned corpus, including benign controls.",
      "Read the attack success rate alongside the benign false-positive rate — one without the other is half a result.",
      "If the run had zero usable samples, expect the rate withheld, not shown as a reassuring zero. Use the CLI for a single-category run when you need one.",
    ],
    expect: "A rate you can act on, or an honest 'not enough usable samples' — never a fabricated 0%.",
    prerequisites: ["At least one harness must exist before the corpus can run."],
    effects: ["Runs the selected harness against the versioned corpus", "May invoke the selected provider; scripted mode measures defences rather than model susceptibility"],
    limits: ["This portal does not offer category or strategy selection; it runs the full corpus only."],
    related: [{ label: "Harnesses", href: "/agents/harnesses" }, { label: "Guardrails", href: "/guardrails" }],
  },
  "/quality/calibration": {
    title: "Judge Calibration",
    subtitle: "Proving an LLM judge agrees with humans before its scores count.",
    why:
      "An uncalibrated judge is a random number generator with good manners. The gate runs " +
      "in two stages because the order matters: if human raters disagree with each other, " +
      "the rubric itself is ambiguous, and calibrating a judge against an ambiguous rubric measures nothing at all.",
    what: "A two-stage gate — inter-rater agreement first, then judge-versus-human correlation — with the result withheld if the first stage fails. The current screen takes manual 1–5 ratings, starting with a clearly labelled deterministic sample.",
    flow: [
      "Replace the sample values with independent human ratings and judge scores, or add and edit rows one by one; the sample is a demo, not evidence.",
      "Check inter-rater agreement first; if humans disagree, fix the rubric before going further.",
      "Run calibration only then, and read the correlation together with its interval and the 500-case warning.",
    ],
    expect: "A judge whose scores you can trust enough to gate other decisions on, or an explicit reason not to yet.",
    effects: ["Calculates a transient calibration report", "No cases, reports, or certification assignments are saved from this screen"],
    limits: ["There is no dataset importer, persistent report, or prompt-level judge assignment here yet."],
    related: [{ label: "A/B Testing", href: "/abtests" }],
  },
  "/governance": {
    title: "Governance",
    subtitle: "What this workspace records, mapped against the controls people get asked about.",
    why:
      "Every control here states its gap beside its evidence. A mapping that lists only " +
      "strengths tells an assessor nothing except that you were selling. This is not a " +
      "compliance assessment and holding it does not make anyone compliant with anything.",
    what: "A control-by-control map: what evidence exists in this workspace, and what gap remains, side by side.",
    flow: [
      "Read a control's evidence and its stated gap together — never one without the other.",
      "Use `assay audit` for the underlying run-log statistics behind any claim here.",
      "Treat this as a starting map for a real assessment, not a substitute for one.",
    ],
    expect: "An honest picture of coverage and gaps you could hand to an assessor without having to caveat it afterward.",
    effects: ["Read-only control and evidence map"],
    related: [{ label: "Red Team", href: "/security/redteam" }, { label: "Judge Calibration", href: "/quality/calibration" }],
  },
  "/integrations": {
    title: "Integrations",
    subtitle: "Where a tested prompt reaches your coding agent, chatbot, or IDE.",
    why:
      "A workspace full of tested prompts is invisible to a coding agent that does not know " +
      "they exist, and useless in a chatbot tab that cannot see the filesystem at all. This " +
      "page is the bridge for both cases, plus the model catalogue that everything else here binds to.",
    what: "Four tabs: AGENTS.md/CLAUDE.md generation for coding agents, MCP config for IDEs and Claude Code, render-only export for chatbots, and the model catalogue.",
    flow: [
      "Coding agent (Codex, Cursor, Claude Code, etc.): generate and write AGENTS.md or CLAUDE.md — it is idempotent and marker-based, so re-running it never erases anything you wrote by hand around it.",
      "IDE or Claude Code specifically: copy the generated MCP config, which already has your real workspace path filled in.",
      "Chatbot (ChatGPT, Claude, Gemini web): pick a prompt, fill its variables, and copy the rendered text — this is text only, no guardrails or evals travel with a paste.",
      "Keep the model catalogue synced so the rest of the workspace is choosing from current models, not a stale seed list.",
    ],
    expect: "Whatever tool you actually work in — agent, IDE, or chat tab — can see and use what is in this workspace.",
    effects: ["Coding-agent tab writes selected marker-delimited instruction files", "MCP and chatbot tabs copy configuration or rendered text", "Model sync may request current catalogue data"],
    limits: ["Chat export carries rendered text only; guardrails, evals, and agent controls do not travel with a paste."],
    related: [{ label: "Token Economy", href: "/context/tokens" }],
  },
  "/datasets": {
    title: "Eval Lab",
    subtitle: "Run embedded or JSONL-backed PromptFile evals with honest denominators.",
    why:
      "Evals attached to a single PromptFile prove that one artifact. This is the layer for " +
      "the broader question — a dataset of cases run across variants or models at once, annotated by a human where automated scoring is not enough.",
    what: "A file-native evaluation runner showing cases, assertions, score intervals, unverified cases, and measured cost for evals already declared in a PromptFile.",
    flow: [
      "Declare inline evals or reference a workspace-relative JSONL/JSON dataset in the PromptFile source; this screen does not create datasets or eval definitions.",
      "Run the selected artifact with its default model or an explicit override.",
      "Inspect case failures, usable denominators, uncertainty, and failure attribution.",
    ],
    expect: "A dataset-level result, not just a handful of eval cases embedded in one file.",
    prerequisites: ["At least one PromptFile must already declare eval cases."],
    effects: ["Run evals may invoke the bound or override model and incur its normal cost", "Results are displayed for this session"],
    limits: ["No dataset upload, dataset editor, or eval authoring control exists on this screen."],
    related: [{ label: "Judge Calibration", href: "/quality/calibration" }],
  },
  "/analytics": {
    title: "Cost Analytics",
    subtitle: "Real spend and usage from the workspace audit log — opt-in, not automatic.",
    why:
      "Cost and latency drift silently once something is live — the prompt has not changed " +
      "but the model provider's pricing or latency has. This used to read a log written only " +
      "when someone ticked \"save\" in the legacy Playground, so most runs left no trace. " +
      "The audit log records every run and evaluate call automatically, from any surface " +
      "(CLI, MCP, REST) — but only once `governance.audit: true` is set, because a log " +
      "nobody configured is a surprise file appearing in a repository.",
    what:
      "Recorded run, artifact, token, cost, latency, and integrity evidence plus a recent-runs table " +
      "— all derived from `.assay/audit/`, the same log Governance reports on.",
    flow: [
      "If this page shows \"auditing is off,\" that is a configuration gap, not a usage gap — turn it on in assay.yaml.",
      "Inspect the Model, Tokens, Cost, and Latency columns in the latest-records table; model grouping and filtering are not yet built into this screen.",
      "Cross-reference against Token Economy if a cost jump looks like a context-size problem rather than a pricing one.",
    ],
    expect: "You notice a cost or latency change from this page before a bill notices it for you — once auditing is on.",
    prerequisites: ["`governance.audit: true` must be enabled before runs occur; historical runs cannot be reconstructed."],
    effects: ["Read-only audit-log evidence", "Shows the latest 100 recorded runs"],
    limits: ["No model grouping, filter, refresh control, chart, or export is available here yet."],
    related: [{ label: "Token Economy", href: "/context/tokens" }, { label: "Governance", href: "/governance" }],
  },
  "/observability": {
    title: "Observability",
    subtitle: "Local audit evidence and OpenTelemetry export readiness, without invented certainty.",
    why:
      "A configured exporter is not proof that a collector received a span. This page separates " +
      "what Assay can prove locally from external delivery, which must be verified in the collector.",
    what: "OpenTelemetry provider and endpoint readiness, content-capture policy, and locally recorded audit-run metadata.",
    flow: [
      "Enable governance.audit in assay.yaml if local audit evidence is required.",
      "Configure an OpenTelemetry SDK and exporter in the process that runs Assay; content capture remains off unless explicitly enabled.",
      "Confirm collector delivery in the destination itself — this read-only status page deliberately reports it as not checked.",
    ],
    expect: "A precise distinction between locally evidenced activity, configured telemetry, and delivery that has not been verified.",
    effects: ["Read-only readiness and local audit evidence"],
    limits: ["Collector delivery must be verified in the collector; this page cannot confirm it."],
    related: [{ label: "Analytics", href: "/analytics" }],
  },
  "/spec": {
    title: "Spec & Plugins",
    subtitle: "The published PromptFile format, and what extends this engine.",
    why:
      "PromptFile is a published spec, not an implementation detail — a file written today " +
      "should still be readable by a tool built in five years. This page is where that " +
      "contract and its plugin extension points are visible, rather than buried in source.",
    what: "The spec fields and version, plus the registered plugins (renderers, providers, evaluators, guardrails, and the rest of the entry-point groups) this installation currently has.",
    flow: [
      "Check the spec major version if you are wondering whether an older file will still be read.",
      "Browse plugins to see what renderers, providers, or evaluators are actually registered here.",
      "Treat unknown fields in a PromptFile as intentional — they round-trip untouched by design, for forward compatibility.",
    ],
    expect: "Clarity on what this specific installation supports, versus what the spec itself allows in general.",
    effects: ["Read-only specification and plugin inventory"],
  },
  "/settings/models": {
    title: "Global Models",
    subtitle: "The model catalogue every prompt binding draws from.",
    why:
      "A model list that never updates quietly steers every new prompt toward whatever was " +
      "current when the workspace was first set up. This keeps the catalogue itself current, separate from any one prompt's binding.",
    what: "A synced, searchable catalogue of models and their metadata, sourced from models.dev with an OpenRouter fallback.",
    flow: [
      "Sync before assuming the list is current — check the timestamp, not just the row count.",
      "Search or filter to find a model by capability or provider.",
      "If the catalogue shows as seed data rather than synced, treat it as a starting point, not a current picture.",
    ],
    expect: "A model list that reflects what is actually available today, not what shipped with the workspace.",
    effects: ["Search is local to the current catalogue", "Sync may request current model metadata from configured sources"],
    related: [{ label: "Model Comparator", href: "/compare" }],
  },
  "/settings": {
    title: "Settings",
    subtitle: "Provider readiness and workbench preferences.",
    why:
      "Provider readiness needs one visible home, but credential values belong in the " +
      "server environment or a secret manager — never browser storage.",
    what: "A secret-free status view showing which backend providers are configured, plus appearance preferences.",
    flow: [
      "Check which providers the backend can currently use.",
      "Configure missing credentials in the backend environment, then restart the server.",
      "Change the local workbench theme without changing runtime configuration.",
    ],
    expect: "An honest readiness signal without any secret value crossing into the browser.",
    effects: ["Provider status is read-only", "Theme is a local workbench preference"],
  },
  "/benchmark": {
    title: "Benchmark Scorecard",
    subtitle: "The exact proof required before Assay can make a 50%-better claim.",
    why:
      "A broad superiority claim hides different product strengths and encourages flattering " +
      "measurements. This scorecard narrows the claim to portable assurance-as-code and keeps " +
      "component evidence separate from comparative proof.",
    what:
      "A source-generated, read-only scorecard: three primary KPIs with formulas, release targets, current Assay evidence, missing comparator results, and the next controlled experiment for each metric.",
    flow: [
      "Confirm that the competitive claim is still withheld.",
      "Inspect each KPI's unit, formula, and 50%-better release threshold.",
      "Separate green component evidence from comparator results that remain not measured.",
      "Download the operator kit and run the shared tasks outside this portal; trial capture and scoring are not interactive portal controls yet.",
    ],
    expect: "A benchmark can become green only through comparable measurements and independent reproduction, never through product rhetoric.",
    effects: ["Read-only generated evidence", "Operator-kit download only; no trial is executed or recorded here"],
    limits: ["This screen cannot capture comparator trials or score newly collected evidence."],
    related: [
      { label: "Delivery Status", href: "/delivery" },
      { label: "Judge Calibration", href: "/quality/calibration" },
    ],
  },
  "/delivery": {
    title: "Delivery Status",
    subtitle: "What is verified, what is being built, and what comes next.",
    why:
      "A long-running improvement programme becomes impossible to trust when progress only " +
      "exists in chat messages. This ledger makes the sequence and its proof visible inside " +
      "the product while refusing to count file presence or intention as completion.",
    what:
      "A source-controlled release ledger grouped into verified, in-progress, and queued " +
      "milestones. Every card states the scope, evidence, and any verification still missing.",
    flow: [
      "Read the three counts for a bounded picture of the tracked release sequence.",
      "Inspect the in-progress card first; its checkpoint states exactly what must happen next.",
      "Open evidence links on verified cards to inspect the shipped behavior in the portal.",
      "Treat queued items as planned work only — they are deliberately not included in the verified count.",
    ],
    expect: "You can distinguish delivered evidence from active work and future work without relying on a status message.",
    effects: ["Read-only source-controlled release ledger"],
    related: [
      { label: "Dashboard", href: "/" },
      { label: "Harnesses", href: "/agents/harnesses" },
      { label: "Benchmark Scorecard", href: "/benchmark" },
    ],
  },
  "/help": {
    title: "Help Centre",
    subtitle: "A searchable, truthful guide to every portal surface and the workflows that connect them.",
    why:
      "A tool should not require its user to already understand its internal vocabulary. This is the map from an intention—write, prove, run, share, or audit—to the page and control that can actually do it today.",
    what:
      "A route-by-route reference built from the same guide records used by the top-right About button. It includes the prompt and agent lifecycles and makes portal-only versus file/CLI-only work explicit.",
    flow: [
      "Choose the prompt or agent journey that matches your goal, or search for the feature you are trying to use.",
      "Open a page card to go there; use the top-right About this page button for its complete steps, prerequisites, effects, and limits.",
      "Follow the related-page links to continue the workflow rather than treating each screen as an isolated tool.",
    ],
    expect: "A clear route from a goal to the right current control, with no invented in-portal capability.",
    effects: ["Read-only orientation and navigation"],
    related: [{ label: "Dashboard", href: "/" }, { label: "Starter Library", href: "/library" }],
  },
};

/** Longest-prefix match so a nested route without its own entry still gets its section's guide. */
export function findGuide(pathname: string): PageGuide | undefined {
  if (PAGE_GUIDES[pathname]) return PAGE_GUIDES[pathname];
  const candidates = Object.keys(PAGE_GUIDES)
    .filter((k) => k !== "/" && pathname.startsWith(k))
    .sort((a, b) => b.length - a.length);
  return candidates.length ? PAGE_GUIDES[candidates[0]] : undefined;
}

export function PageGuideModal({
  guide,
  onClose,
}: {
  guide: PageGuide;
  onClose: () => void;
}) {
  return (
    <Sheet
      eyebrow="About this page"
      title={guide.title}
      subtitle={guide.subtitle}
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-500">
              Expected result
            </p>
            <p className="text-sm font-medium">{guide.expect}</p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Got it
          </button>
        </div>
      }
    >
      <div className="space-y-5">
        <Section label="Why this page exists">
          <p className="text-sm leading-relaxed">{guide.why}</p>
        </Section>
        <Section label="What it does">
          <p className="text-sm leading-relaxed text-muted-foreground">{guide.what}</p>
        </Section>
        {guide.prerequisites && guide.prerequisites.length > 0 && (
          <Section label="Before you start">
            <ul className="space-y-1.5 text-sm text-muted-foreground">
              {guide.prerequisites.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}
        {guide.effects && guide.effects.length > 0 && (
          <Section label="What happens when you use it">
            <div className="flex flex-wrap gap-2">
              {guide.effects.map((effect) => (
                <span
                  key={effect}
                  className="rounded-full border border-sky-500/30 bg-sky-500/5 px-2.5 py-1 text-[11px] font-medium text-sky-300"
                >
                  {effect}
                </span>
              ))}
            </div>
          </Section>
        )}
        {guide.limits && guide.limits.length > 0 && (
          <Section label="Not on this screen">
            <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-3">
              <ul className="space-y-1.5 text-xs leading-relaxed text-amber-100/85">
                {guide.limits.map((limit) => (
                  <li key={limit} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                    <span>{limit}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Section>
        )}
        <Section label="Step-by-step flow">
          <div className="space-y-0">
            {guide.flow.map((step, i) => (
              <div key={i} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-emerald-500/40 bg-emerald-500/10 text-xs font-bold text-emerald-500">
                    {i + 1}
                  </div>
                  {i < guide.flow.length - 1 && (
                    <div className="my-0.5 h-full w-px flex-1 bg-border" />
                  )}
                </div>
                <div className={i < guide.flow.length - 1 ? "pb-5" : ""}>
                  <p className="pt-0.5 text-sm font-medium leading-snug">{step}</p>
                  {i < guide.flow.length - 1 && (
                    <p className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground/60">
                      then
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Section>
        {guide.related && guide.related.length > 0 && (
          <Section label="Related pages">
            <div className="flex flex-wrap gap-2">
              {guide.related.map((r) => (
                <Link
                  key={r.href}
                  href={r.href}
                  onClick={onClose}
                  className="rounded-lg border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  {r.label} →
                </Link>
              ))}
            </div>
          </Section>
        )}
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// portal-wide map
// ---------------------------------------------------------------------------

type Layer = {
  label: string;
  note: string;
  boxes: { label: string; href: string }[];
};

const LAYERS: Layer[] = [
  {
    label: "1 · Write and organise",
    note: "Everything begins as a PromptFile — a text file with a template, a model binding, and its own tests.",
    boxes: [
      { label: "Starter Library", href: "/library" },
      { label: "Prompt Studio", href: "/studio" },
      { label: "All Prompts", href: "/prompts" },
    ],
  },
  {
    label: "2 · Prove it works",
    note: "An artifact with no eval cases passes every run by default. That is not the same as working.",
    boxes: [
      { label: "Eval Lab", href: "/datasets" },
      { label: "A/B Testing", href: "/abtests" },
      { label: "Model Comparator", href: "/compare" },
      { label: "Guardrails", href: "/guardrails" },
    ],
  },
  {
    label: "3 · Go beyond one call",
    note: "Multi-step or tool-using work outgrows a single prompt.",
    boxes: [
      { label: "Harnesses", href: "/agents/harnesses" },
      { label: "Loops", href: "/agents/loops" },
      { label: "Memory", href: "/agents/memory" },
    ],
  },
  {
    label: "4 · Earn trust",
    note: "Working is not the same as safe, or believed. This is the evidence layer.",
    boxes: [
      { label: "Red Team", href: "/security/redteam" },
      { label: "Judge Calibration", href: "/quality/calibration" },
      { label: "Governance", href: "/governance" },
    ],
  },
  {
    label: "5 · Put it to work",
    note: "The same tested artifact reaches wherever you actually work.",
    boxes: [
      { label: "Integrations", href: "/integrations" },
      { label: "Token Economy", href: "/context/tokens" },
    ],
  },
  {
    label: "6 · Watch it run",
    note: "Once it is live, this is where drift becomes visible.",
    boxes: [
      { label: "Analytics", href: "/analytics" },
      { label: "Observability", href: "/observability" },
    ],
  },
];

const CROSS_CUTTING = [
  { label: "Help Centre", href: "/help" },
  { label: "Dashboard", href: "/" },
  { label: "Delivery Status", href: "/delivery" },
  { label: "Benchmark", href: "/benchmark" },
  { label: "Projects", href: "/projects" },
  { label: "Spec & Plugins", href: "/spec" },
  { label: "Global Models", href: "/settings/models" },
  { label: "Settings", href: "/settings" },
];

export function PortalMapModal({ onClose }: { onClose: () => void }) {
  const [showCrossCutting, setShowCrossCutting] = useState(false);

  return (
    <Sheet
      eyebrow="Portal map"
      title="How Assay fits together"
      subtitle="One prompt's path from a first draft to production evidence — click any box to go there."
      onClose={onClose}
      footer={
        <p className="text-xs text-muted-foreground">
          Lost on any single page? Its own <strong>?</strong> button (top right, everywhere) explains
          that page specifically — why it exists, what it does, and the flow to follow.
        </p>
      }
    >
      <div className="space-y-1">
        <div className="rounded-xl border border-sky-500/20 bg-sky-500/[0.04] p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-sky-400">
            Shared source of truth
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Library and Studio write PromptFiles. The portal, CLI, REST API, and MCP server read the same files;
            evals, experiments, harnesses, loops, and red team then produce evidence from them. Audit-enabled runs feed
            Governance, Analytics, and Observability. Delivery and Benchmark read source-controlled product evidence—they do not run your workspace.
          </p>
        </div>
        {LAYERS.map((layer, i) => (
          <div key={layer.label}>
            <div className="rounded-xl border bg-background p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-violet-400">
                {layer.label}
              </p>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{layer.note}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {layer.boxes.map((b) => (
                  <Link
                    key={b.href}
                    href={b.href}
                    onClick={onClose}
                    className="rounded-lg border bg-muted/40 px-3 py-1.5 text-xs font-semibold hover:border-violet-500/40 hover:bg-violet-500/10 hover:text-violet-400 transition-colors"
                  >
                    {b.label}
                  </Link>
                ))}
              </div>
            </div>
            {i < LAYERS.length - 1 && (
              <div className="flex justify-center py-1">
                <ArrowDown className="h-4 w-4 text-muted-foreground/40" />
              </div>
            )}
          </div>
        ))}

        <div className="pt-4">
          <button
            onClick={() => setShowCrossCutting(!showCrossCutting)}
            className="flex w-full items-center justify-between rounded-xl border border-dashed bg-background/50 p-4 text-left"
          >
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">
                Cross-cutting
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Not a pipeline stage — used from anywhere, at any point.
              </p>
            </div>
            <ChevronDown
              className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${showCrossCutting ? "rotate-180" : ""}`}
            />
          </button>
          {showCrossCutting && (
            <div className="mt-2 flex flex-wrap gap-2 rounded-xl border border-dashed p-4">
              {CROSS_CUTTING.map((b) => (
                <Link
                  key={b.href}
                  href={b.href}
                  onClick={onClose}
                  className="rounded-lg border bg-muted/40 px-3 py-1.5 text-xs font-semibold hover:border-violet-500/40 hover:bg-violet-500/10 hover:text-violet-400 transition-colors"
                >
                  {b.label}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </Sheet>
  );
}

export { HelpCircle, MapIcon };

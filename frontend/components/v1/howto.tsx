"use client";

/**
 * Inline guidance — what this page is for, and the command that does it elsewhere.
 *
 * A workbench that only works when you already know the vocabulary is a workbench for
 * the person who wrote it. Nobody should have to read the repository to find out what a
 * harness is, and nobody who prefers the terminal should have to guess the command.
 *
 * Two deliberate constraints:
 *
 * **Collapsed by default, remembered per section.** Guidance that cannot be dismissed
 * becomes furniture people stop reading. This opens on first visit and stays shut once
 * closed, using component state — never browser storage, which is unavailable here.
 *
 * **Every concept states the same thing three ways**: what it is, why it exists, and the
 * command. The third is what makes the UI a teaching surface for the CLI rather than a
 * competing way to do the same job.
 */

import React, { useState } from "react";
import { Check, ChevronDown, Copy, Terminal } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export type Concept = {
  /** One sentence. What the reader is looking at. */
  what: string;
  /** Why it exists — the failure it prevents. This is the part that is usually missing. */
  why: string;
  /** The equivalent CLI, so the UI teaches the terminal instead of competing with it. */
  commands?: { command: string; does: string }[];
  /** Where to read more, inside the repo. */
  reading?: { label: string; href: string }[];
};

/**
 * The vocabulary this product invented or borrowed, in one place.
 *
 * Kept centrally rather than inline per page so the same term cannot be explained two
 * different ways in two places — which is how documentation starts lying.
 */
export const CONCEPTS: Record<string, Concept> = {
  harness: {
    what:
      "A harness is an agent declared in a file: the loop, the tools it may call, the " +
      "budget it may spend, what it remembers, and the controls that stop it.",
    why:
      "Running an agent is easy; knowing whether it worked is not. A harness produces a " +
      "trajectory — the record of what it actually did — so assertions can check the path, " +
      "not just the final answer. An agent can reach the right result through a tool call " +
      "it should never have made.",
    commands: [
      { command: "assay new my/agent --kind harness", does: "create one" },
      { command: "assay run my/agent -v goal='find the bug'", does: "run it" },
      { command: "assay test my/agent", does: "check its trajectory assertions" },
    ],
    reading: [{ label: "Harness engineering", href: "/docs/knowledge/harness-engineering.md" }],
  },
  loop: {
    what:
      "A loop runs steps, verifies, and decides whether to go again — the outer loop " +
      "around an agent rather than the agent itself.",
    why:
      "Errors compound. A 90%-accurate step feeding another 90%-accurate step does not " +
      "yield 90%, so by step 18 of a 20-step chain you can have a confident, coherent, " +
      "wrong result. Verification runs at every handoff, not only at the end, and a loop " +
      "that verified nothing reports 'not checked' rather than success.",
    commands: [
      { command: "assay run my/pipeline", does: "run one loop to completion" },
      { command: "assay test my/pipeline", does: "assert it converged and every step verified" },
    ],
    reading: [{ label: "Loop engineering", href: "/docs/knowledge/loop-engineering.md" }],
  },
  memory: {
    what:
      "What an agent carries from one run into the next, recalled by a hybrid score with " +
      "no embeddings involved.",
    why:
      "Without memory every run starts cold and repeats work it already did. Recall ranks " +
      "exact identifiers — file paths, tool names — above fuzzy similarity, because that is " +
      "what agents actually search by, and it keeps the whole thing working offline.",
    commands: [
      { command: "assay memory search 'billing/invoice.py'", does: "search what was remembered" },
      { command: "assay memory forget --namespace research", does: "clear a namespace" },
    ],
  },
  redteam: {
    what:
      "Indirect prompt injection run against a harness, scored against a versioned corpus " +
      "of attacks and benign controls.",
    why:
      "Attacks arrive through tool output — content the agent did not write and cannot " +
      "vouch for. Benign controls sit alongside the attacks so a detector that flags " +
      "everything scores badly rather than perfectly. None of this is safety: it raises the " +
      "cost of an attack, it does not close the class.",
    commands: [
      { command: "assay redteam my/agent", does: "run the full corpus" },
      { command: "assay redteam my/agent --category tool_poisoning", does: "one category" },
    ],
    reading: [{ label: "Agent security", href: "/docs/knowledge/agent-security.md" }],
  },
  calibration: {
    what:
      "Proving an LLM judge agrees with humans before its scores are allowed to count.",
    why:
      "An uncalibrated judge is a random number generator with good manners. The gate has " +
      "two stages because the order matters: if the human raters disagree, the rubric is " +
      "ambiguous and calibrating against it measures nothing at all.",
    commands: [{ command: "assay judge calibrate --cases labelled.json", does: "run the gate" }],
  },
  tokens: {
    what:
      "What an agent has to load to know what is available, versus loading everything.",
    why:
      "Context is a budget, not a bucket. A compact index costs a fraction of the full " +
      "library, and the headroom goes to the actual task. The saving is measured against " +
      "this workspace and shown beside its denominator so the claim can be checked.",
    commands: [{ command: "assay tokens", does: "measure this workspace" }],
    reading: [{ label: "Context engineering", href: "/docs/knowledge/context-engineering.md" }],
  },
  governance: {
    what:
      "What this workspace records, mapped against the controls people get asked about.",
    why:
      "Every control states its gap beside its evidence. A mapping that lists only " +
      "strengths tells an assessor nothing except that you were selling. This is not a " +
      "compliance assessment and does not make anyone compliant with anything.",
    commands: [
      { command: "assay audit", does: "run-log statistics" },
      { command: "assay governance report", does: "the control map" },
    ],
  },
  packs: {
    what: "Starter PromptFiles you can copy into this workspace.",
    why:
      "Every starter is a real PromptFile with its own eval cases — the same format your " +
      "own prompts use. Installing copies the file unchanged; nothing is templated, and " +
      "files you already have are never overwritten.",
    commands: [{ command: "assay ls", does: "list what is installed" }],
  },
};

export function HowTo({
  concept,
  title = "What is this?",
  defaultOpen = false,
}: {
  concept: keyof typeof CONCEPTS | Concept;
  title?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const c = typeof concept === "string" ? CONCEPTS[concept] : concept;
  if (!c) return null;

  return (
    <Card className="border-dashed">
      <CardContent className="p-0">
        <button
          onClick={() => setOpen(!open)}
          className="w-full flex items-center justify-between gap-3 px-5 py-3 text-left hover:bg-muted/30 transition-colors"
        >
          <span className="text-xs font-medium text-muted-foreground">{title}</span>
          <ChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>

        {open && (
          <div className="px-5 pb-5 space-y-3 border-t border-border pt-4">
            <p className="text-sm leading-relaxed">{c.what}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{c.why}</p>

            {c.commands && c.commands.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
                  <Terminal className="h-3 w-3" />
                  Same thing from the terminal
                </p>
                {c.commands.map((cmd) => (
                  <CommandRow key={cmd.command} command={cmd.command} does={cmd.does} />
                ))}
              </div>
            )}

            {c.reading && c.reading.length > 0 && (
              <p className="text-[11px] text-muted-foreground pt-1">
                Further reading:{" "}
                {c.reading.map((r, i) => (
                  <React.Fragment key={r.href}>
                    {i > 0 && " · "}
                    <code className="font-mono">{r.href.replace(/^\//, "")}</code>
                  </React.Fragment>
                ))}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * A copyable command.
 *
 * Uses the async clipboard API with a silent fallback: copying is a convenience, and a
 * denied clipboard permission should not throw an error at someone who was only reading.
 */
export function CommandRow({ command, does }: { command: string; does?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — the command is still readable on screen */
    }
  };

  return (
    <div className="flex items-center gap-2 group">
      <code className="flex-1 text-[11px] font-mono bg-muted rounded px-2 py-1.5 text-muted-foreground truncate">
        $ {command}
      </code>
      {does && (
        <span className="text-[10px] text-muted-foreground shrink-0 hidden sm:inline">
          {does}
        </span>
      )}
      <button
        onClick={copy}
        className="shrink-0 p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
        aria-label={`Copy: ${command}`}
      >
        {copied ? (
          <Check className="h-3 w-3 text-emerald-400" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </button>
    </div>
  );
}

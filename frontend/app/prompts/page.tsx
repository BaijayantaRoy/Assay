"use client";

/**
 * All Prompts — every PromptFile in this workspace, browsable and searchable.
 *
 * Used to read `/prompts/all`, the legacy 0.x database — a second, disconnected catalogue
 * from the one the CLI, MCP server, and Starter Library actually use. That meant a prompt
 * installed from the Starter Library or written with `assay new` never showed up here, and
 * a "prompt" created on this page was invisible to `assay ls`. Now both read the same
 * `/v1/prompts`, backed by the real file store.
 *
 * There is no server-side semantic search here (the legacy page had one, backed by a
 * vector DB this page no longer talks to) — filtering is a local substring match over id,
 * name, description, and tags. Overstating it as "semantic" would be exactly the kind of
 * claim this project exists to avoid making.
 */

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { FileText, MessageSquare, Search } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorPanel, PageHeader } from "@/components/v1/shell";
import { listPrompts, PromptSummary } from "@/lib/v1";

export default function PromptsPage() {
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [query, setQuery] = useState("");
  const [ns, setNs] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    listPrompts()
      .then(setPrompts)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const namespaces = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of prompts) {
      const seg = p.id.includes("/") ? p.id.split("/")[0] : "(none)";
      counts[seg] = (counts[seg] || 0) + 1;
    }
    return Object.entries(counts).sort();
  }, [prompts]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return prompts.filter((p) => {
      const seg = p.id.includes("/") ? p.id.split("/")[0] : "(none)";
      if (ns !== "all" && seg !== ns) return false;
      if (!q) return true;
      return (
        p.id.toLowerCase().includes(q) ||
        (p.name || "").toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q) ||
        p.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [prompts, query, ns]);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        icon={FileText}
        title="All Prompts"
        subtitle="Every PromptFile in this workspace — the same catalogue the CLI reads."
        note={
          <>
            Grouped by <strong>namespace</strong> — the first segment of a prompt&apos;s id (for
            example <code className="font-mono">agents/</code> in{" "}
            <code className="font-mono">agents/code-reviewer</code>). That grouping is what{" "}
            <Link href="/projects" className="underline hover:text-foreground">
              Projects
            </Link>{" "}
            shows too, from the same data.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Filter by id, name, description, or tag…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <button onClick={() => setNs("all")} className={chip(ns === "all")}>
          all {prompts.length}
        </button>
        {namespaces.map(([name, n]) => (
          <button key={name} onClick={() => setNs(name)} className={chip(ns === name)}>
            {name} {n}
          </button>
        ))}
      </div>

      <div className="grid gap-3">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="p-4">
              <div className="flex items-center gap-4">
                <Skeleton className="h-10 w-10 rounded-md" />
                <div className="flex-1">
                  <Skeleton className="h-4 w-40 mb-2" />
                  <Skeleton className="h-3 w-56" />
                </div>
              </div>
            </Card>
          ))
        ) : visible.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-medium">
              {query || ns !== "all" ? "No results found" : "No prompts yet"}
            </p>
            <p className="text-sm mt-1">
              {query || ns !== "all" ? (
                "Try a different filter."
              ) : (
                <>
                  Install one from the{" "}
                  <Link href="/library" className="underline hover:text-foreground">
                    Starter Library
                  </Link>
                  , or write one in{" "}
                  <Link href="/studio" className="underline hover:text-foreground">
                    Prompt Studio
                  </Link>
                  .
                </>
              )}
            </p>
          </div>
        ) : (
          visible.map((prompt) => (
            <Link key={prompt.id} href={`/prompts/${prompt.id}`}>
              <Card className="p-4 hover:border-primary/50 hover:shadow-sm transition-all duration-200 group">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 group-hover:bg-primary/20 transition-colors">
                      <FileText className="h-5 w-5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="font-semibold group-hover:text-primary transition-colors truncate">
                          {prompt.name || prompt.id}
                        </h4>
                        <span className="text-[10px] font-mono text-muted-foreground shrink-0">
                          {prompt.id}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground line-clamp-1">
                        {prompt.description || "No description"}
                      </p>
                      {prompt.tags.length > 0 && (
                        <div className="flex gap-1 mt-1.5 flex-wrap">
                          {prompt.tags.map((tag) => (
                            <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0">
                    <span
                      title={
                        prompt.has_evals
                          ? "Carries at least one eval case — run `assay test` to see if it passes"
                          : "No eval case attached — passes by default, which is not the same as working"
                      }
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                        prompt.has_evals
                          ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
                          : "text-muted-foreground bg-muted/40 border-border"
                      }`}
                    >
                      {prompt.has_evals ? "has evals" : "no evals"}
                    </span>
                  </div>
                </div>
              </Card>
            </Link>
          ))
        )}
      </div>

      {!loading && visible.length > 0 && (
        <p className="text-xs text-muted-foreground text-center">
          {visible.length} of {prompts.length} prompt{prompts.length !== 1 ? "s" : ""} shown
        </p>
      )}
    </div>
  );
}

const chip = (active: boolean) =>
  `px-2.5 py-1 rounded-lg text-[11px] font-medium border transition-colors ${
    active
      ? "bg-indigo-500/10 text-indigo-400 border-indigo-500/30"
      : "text-muted-foreground border-transparent hover:text-foreground"
  }`;

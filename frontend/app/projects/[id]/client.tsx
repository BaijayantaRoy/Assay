"use client";

/**
 * One namespace — every prompt whose id starts with `{namespace}/`.
 *
 * There is no project row to fetch; this filters the same `/v1/prompts` list the parent
 * page reads, client-side, by the id prefix. "(none)" is the bucket for ids with no slash
 * at all — those are namespace-less by construction, not an error.
 */

import React, { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileText, Folder, Search } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorPanel } from "@/components/v1/shell";
import { listPrompts, PromptSummary } from "@/lib/v1";

export default function Client({ params }: { params: Promise<{ id: string }> }) {
  const { id: ns } = use(params);
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    listPrompts().then(setPrompts).catch(setError).finally(() => setLoading(false));
  }, []);

  const items = useMemo(() => {
    const inNamespace = prompts.filter((p) => {
      const seg = p.id.includes("/") ? p.id.split("/")[0] : "(none)";
      return seg === ns;
    });
    const q = query.trim().toLowerCase();
    if (!q) return inNamespace;
    return inNamespace.filter(
      (p) =>
        p.id.toLowerCase().includes(q) ||
        (p.name || "").toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q),
    );
  }, [prompts, ns, query]);

  return (
    <div className="space-y-6 animate-fade-in">
      <Link href="/projects" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft className="h-4 w-4" /> Projects
      </Link>

      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
          <Folder className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">{ns}</h1>
          <p className="text-sm text-muted-foreground">
            {loading ? "Loading…" : `${items.length} prompt${items.length !== 1 ? "s" : ""} with this prefix`}
          </p>
        </div>
      </div>

      {error != null && <ErrorPanel error={error} />}

      <div className="relative">
        <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Filter within this namespace…" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>

      <div className="grid gap-3">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
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
        ) : items.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-medium">{query ? "No prompts match your filter" : "Nothing here yet"}</p>
            <p className="text-sm mt-1">
              {query ? "Try a different search term." : (
                <>Write a prompt with id <code className="font-mono">{ns}/…</code> in{" "}
                  <Link href="/studio" className="underline hover:text-foreground">Prompt Studio</Link> to populate this namespace.</>
              )}
            </p>
          </div>
        ) : (
          items.map((prompt) => (
            <Link key={prompt.id} href={`/prompts/${prompt.id}`}>
              <Card className="p-4 hover:border-primary/50 hover:shadow-sm transition-all duration-200 group">
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 group-hover:bg-primary/20 transition-colors">
                    <FileText className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <h4 className="font-semibold group-hover:text-primary transition-colors">
                      {prompt.name || prompt.id}
                    </h4>
                    <p className="text-sm text-muted-foreground line-clamp-1">
                      {prompt.description || "No description"}
                    </p>
                    {prompt.tags.length > 0 && (
                      <div className="flex gap-1 mt-1.5 flex-wrap">
                        {prompt.tags.slice(0, 3).map((tag) => (
                          <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0">{tag}</Badge>
                        ))}
                        {prompt.tags.length > 3 && (
                          <span className="text-[10px] text-muted-foreground">+{prompt.tags.length - 3}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

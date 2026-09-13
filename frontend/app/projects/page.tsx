"use client";

/**
 * Projects — now namespaces, not a database entity.
 *
 * The legacy version created rows in a `Project` table, scoped to an `organization_id`,
 * with its own create/delete lifecycle. There is no equivalent in the file-based model:
 * a PromptFile's id is just a path (`support/refund-triage`), and the "project" was never
 * anything but the string before the first slash. Keeping a separate database entity for
 * that would mean two systems could disagree about which project a prompt belongs to.
 *
 * So this page derives its grouping from `/v1/prompts` directly. Giving a new prompt an id
 * like `billing/dunning-email` is what creates the `billing` group — there is nothing to
 * create or delete beyond writing prompts with the ids you want.
 */

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Folder, Library as LibraryIcon, Wand2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorPanel, PageHeader } from "@/components/v1/shell";
import { listPrompts, PromptSummary } from "@/lib/v1";

export default function ProjectsPage() {
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    listPrompts().then(setPrompts).catch(setError).finally(() => setLoading(false));
  }, []);

  const namespaces = useMemo(() => {
    const groups: Record<string, PromptSummary[]> = {};
    for (const p of prompts) {
      const ns = p.id.includes("/") ? p.id.split("/")[0] : "(none)";
      (groups[ns] ||= []).push(p);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [prompts]);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        icon={Folder}
        title="Projects"
        subtitle="Derived from prompt ids — the segment before the first slash."
        note={
          <>
            There is no separate project to create. Give a prompt an id like{" "}
            <code className="font-mono">billing/dunning-email</code> in{" "}
            <Link href="/studio" className="underline hover:text-foreground">Prompt Studio</Link> and{" "}
            <code className="font-mono">billing</code> appears here on its own.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="p-6">
              <Skeleton className="h-4 w-32 mb-3" />
              <Skeleton className="h-3 w-48" />
            </Card>
          ))
        ) : (
          namespaces.map(([ns, items]) => (
            <Link key={ns} href={`/projects/${encodeURIComponent(ns)}`} className="group">
              <Card className="p-6 hover:border-primary/50 hover:shadow-md hover:shadow-primary/5 transition-all duration-200 h-full">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 group-hover:bg-primary/20 transition-colors">
                    <Folder className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-semibold group-hover:text-primary transition-colors truncate">
                      {ns}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {items.length} prompt{items.length !== 1 ? "s" : ""}
                    </p>
                  </div>
                </div>
              </Card>
            </Link>
          ))
        )}
      </div>

      {!loading && namespaces.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <Folder className="h-12 w-12 mx-auto mb-4 opacity-30" />
          <p className="text-lg font-medium">No prompts yet</p>
          <p className="text-sm mt-1 flex items-center justify-center gap-4">
            <Link href="/library" className="inline-flex items-center gap-1.5 underline hover:text-foreground">
              <LibraryIcon className="h-3.5 w-3.5" /> Starter Library
            </Link>
            <Link href="/studio" className="inline-flex items-center gap-1.5 underline hover:text-foreground">
              <Wand2 className="h-3.5 w-3.5" /> Prompt Studio
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}

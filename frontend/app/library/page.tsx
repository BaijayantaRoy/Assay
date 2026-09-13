"use client";

/**
 * Starter Library — real PromptFiles you can install into the workspace.
 *
 * This page was broken in a way worth recording. Twenty-three starter prompts existed in
 * the backend as Python dicts, and this page fetched `/prompts/all` instead — the user's
 * own database, which is empty on a fresh install. So the library was always empty, and
 * the content it existed to show was unreachable from any surface.
 *
 * The starters are now PromptFiles in `packs/`, served by `/v1/packs`. They validate
 * against the published spec and carry their own eval cases, which matters more than it
 * sounds: this is the first screen where a newcomer sees what the format actually looks
 * like, and a starter that is not itself a PromptFile would teach the wrong thing.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Library, Download, Check, FileText, Bot, RefreshCw, Search, Variable,
  CheckCircle2, AlertTriangle, PackageCheck,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Empty, ErrorPanel, Loading, PageHeader } from "@/components/v1/shell";
import { HowTo } from "@/components/v1/howto";
import { InstallResult, Pack, PackItem, installPack, listPacks } from "@/lib/v1";

const KIND_ICON: Record<string, React.ElementType> = {
  harness: Bot,
  loop: RefreshCw,
  prompt: FileText,
};

export default function LibraryPage() {
  const [packs, setPacks] = useState<Pack[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<InstallResult | null>(null);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listPacks()
      .then((d) => setPacks(d.packs))
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const allItems = useMemo(() => packs.flatMap((pack) => pack.items), [packs]);
  const totalCount = allItems.length;
  const categories = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of allItems) {
      const namespace = item.id.split("/")[0] || "misc";
      counts[namespace] = (counts[namespace] || 0) + 1;
    }
    return Object.entries(counts).sort();
  }, [allItems]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allItems.filter((item) => {
      const ns = item.id.split("/")[0];
      if (category !== "all" && ns !== category) return false;
      if (!q) return true;
      return (
        item.id.toLowerCase().includes(q) ||
        (item.name || "").toLowerCase().includes(q) ||
        item.summary.toLowerCase().includes(q) ||
        item.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [allItems, query, category]);

  const selectionKey = (item: PackItem) => `${item.pack_id}:${item.id}`;
  const toggle = (item: PackItem) =>
    setSelected((prev) => {
      const next = new Set(prev);
      const key = selectionKey(item);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const install = useCallback(
    async (items: PackItem[]) => {
      if (!items.length) return;
      setInstalling(true);
      setError(null);
      try {
        const grouped = new Map<string, string[]>();
        for (const item of items) {
          grouped.set(item.pack_id, [...(grouped.get(item.pack_id) || []), item.id]);
        }
        const results = await Promise.all(
          [...grouped].map(([packId, ids]) => installPack(packId, ids)),
        );
        setResult({
          pack: results.length === 1 ? results[0].pack : "multiple",
          installed: results.flatMap((entry) => entry.installed),
          skipped: results.flatMap((entry) => entry.skipped),
          failed: results.flatMap((entry) => entry.failed),
          counts: {
            installed: results.reduce((sum, entry) => sum + entry.counts.installed, 0),
            skipped: results.reduce((sum, entry) => sum + entry.counts.skipped, 0),
            failed: results.reduce((sum, entry) => sum + entry.counts.failed, 0),
          },
          note: results.map((entry) => entry.note).filter(Boolean).join(" ") || null,
        });
        setSelected(new Set());
      } catch (e) {
        setError(e);
      } finally {
        setInstalling(false);
      }
    },
    [],
  );

  if (loading) return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Starter Library</h1>
        <p className="mt-1 text-sm text-muted-foreground">Reviewable PromptFile packs</p>
      </div>
      <Loading label="Loading starter packs…" />
    </div>
  );

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={Library}
        title="Starter Library"
        subtitle={`${totalCount} reviewable PromptFiles across ${packs.length} domain packs`}
        gradient="from-indigo-500/10 via-violet-500/5"
        iconGradient="from-indigo-500 to-violet-500"
        border="border-indigo-500/20"
        note={
          <>
            Every starter here is a real <strong>PromptFile</strong> — the same format your
            own prompts use, validated against the published spec, with eval scope shown
            on each card. A <strong>render contract</strong> proves the template and inputs,
            not semantic quality from every possible model. Installing copies the file
            into your prompts directory; nothing is rewritten and existing files are
            never overwritten.
          </>
        }
        action={
          selected.size > 0 ? (
            <Button
              onClick={() => install(allItems.filter((item) => selected.has(selectionKey(item))))}
              disabled={installing}
              className="gap-2 shrink-0"
            >
              <Download className={`h-4 w-4 ${installing ? "animate-pulse" : ""}`} />
              Install {selected.size}
            </Button>
          ) : undefined
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <HowTo concept="packs" />
      {result && <InstallSummary result={result} />}

      {totalCount === 0 ? (
        <Empty
          icon={Library}
          title="No starter packs found"
          hint={
            <>
              Packs live in <code className="font-mono">packs/</code> in the repository.
              Each directory there becomes a pack.
            </>
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search starters…"
                className="pl-8"
              />
            </div>
            <button onClick={() => setCategory("all")} className={chip(category === "all")}>
              all {totalCount}
            </button>
            {categories.map(([name, n]) => (
              <button
                key={name}
                onClick={() => setCategory(name)}
                className={chip(category === name)}
              >
                {name} {n}
              </button>
            ))}
          </div>

          <p className="text-xs text-muted-foreground">
            {visible.length} of {totalCount} shown across {packs.length} packs
            {selected.size > 0 && <> · {selected.size} selected</>}
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {visible.map((item) => (
              <StarterCard
                key={selectionKey(item)}
                item={item}
                selected={selected.has(selectionKey(item))}
                onToggle={() => toggle(item)}
                onInstall={() => install([item])}
                installing={installing}
              />
            ))}
          </div>
        </>
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

function StarterCard({
  item, selected, onToggle, onInstall, installing,
}: {
  item: PackItem;
  selected: boolean;
  onToggle: () => void;
  onInstall: () => void;
  installing: boolean;
}) {
  const Icon = KIND_ICON[item.kind] || FileText;
  return (
    <Card
      className={`flex flex-col transition-colors ${
        selected ? "border-indigo-500/50 bg-indigo-500/5" : "hover:border-border/80"
      }`}
    >
      <CardContent className="p-5 space-y-3 flex-1 flex flex-col">
        <div className="flex items-start gap-2">
          <button
            onClick={onToggle}
            className={`mt-0.5 h-4 w-4 shrink-0 rounded border flex items-center justify-center ${
              selected ? "bg-indigo-500 border-indigo-500" : "border-border"
            }`}
            aria-label={selected ? "Deselect" : "Select"}
          >
            {selected && <Check className="h-3 w-3 text-white" />}
          </button>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold leading-snug">{item.name || item.id}</p>
            <p className="text-[11px] font-mono text-muted-foreground truncate">{item.id}</p>
            <p className="text-[10px] text-muted-foreground">{item.pack_id} pack</p>
          </div>
          <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed flex-1">{item.summary}</p>

        <div className="flex flex-wrap items-center gap-1.5">
          {item.has_evals && (
            <Badge
              variant="outline"
              className="text-[10px] text-emerald-400 border-emerald-500/30 gap-1"
            >
              <CheckCircle2 className="h-2.5 w-2.5" />
              {item.eval_scope === "render-contract-only" ? "render contract" : "evals attached"}
            </Badge>
          )}
          {item.variables.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono text-muted-foreground"
            >
              <Variable className="h-2.5 w-2.5" />
              {v}
            </span>
          ))}
        </div>

        <details>
          <summary className="text-[11px] text-muted-foreground cursor-pointer hover:text-foreground">
            Preview
          </summary>
          <pre className="mt-2 text-[10px] font-mono whitespace-pre-wrap bg-muted/50 rounded p-2 max-h-40 overflow-auto">
            {item.body_preview}
          </pre>
        </details>

        <Button
          variant="outline"
          size="sm"
          onClick={onInstall}
          disabled={installing}
          className="w-full gap-1.5 text-xs"
        >
          <Download className="h-3 w-3" />
          Install
        </Button>
      </CardContent>
    </Card>
  );
}

function InstallSummary({ result }: { result: InstallResult }) {
  const { counts } = result;
  const tone = counts.failed
    ? "border-red-500/40 bg-red-500/5"
    : counts.installed
      ? "border-emerald-500/40 bg-emerald-500/5"
      : "border-amber-500/40 bg-amber-500/5";

  return (
    <Card className={tone}>
      <CardContent className="p-4 flex items-start gap-3">
        {counts.failed ? (
          <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
        ) : (
          <PackageCheck className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
        )}
        <div className="space-y-1 min-w-0">
          <p className="text-sm font-semibold">
            {counts.installed} installed
            {counts.skipped > 0 && ` · ${counts.skipped} skipped`}
            {counts.failed > 0 && ` · ${counts.failed} failed`}
          </p>
          {result.installed.length > 0 && (
            <p className="text-[11px] font-mono text-muted-foreground break-all">
              {result.installed.map((i) => i.path).join(", ")}
            </p>
          )}
          {result.note && <p className="text-xs text-muted-foreground">{result.note}</p>}
          {result.failed.map((f) => (
            <p key={f.file} className="text-[11px] text-red-400">
              {f.file}: {f.error}
            </p>
          ))}
          {counts.installed > 0 && (
            <p className="text-xs text-muted-foreground">
              Run <code className="font-mono">assay test</code> to check them, or{" "}
              <Link href="/prompts" className="underline hover:text-foreground">open All Prompts</Link>{" "}
              to inspect the installed PromptFile.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

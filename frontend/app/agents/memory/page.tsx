"use client";

/**
 * Agent memory — what carried over between runs.
 *
 * Memory is the difference between an agent that starts cold every time and one that
 * remembers it already looked. Recall here is hybrid and deliberately embedding-free:
 * entity matches rank above keyword, keyword above recency, recency above outcome. That
 * keeps memory usable offline and beats vector search on the thing agents actually recall
 * by — exact identifiers like `billing/invoice.py`.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  Brain, Search, Clock, Tag, Link2, Layers, Database,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Empty, ErrorPanel, Loading, PageHeader, Stat, shortId,
} from "@/components/v1/shell";
import { HowTo } from "@/components/v1/howto";
import {
  MemoryOverview, MemoryRecord, memoryOverview, searchMemory,
} from "@/lib/v1";

const WEIGHTS = [
  { signal: "entity", weight: 3.0, why: "exact identifiers — file paths, tool names, ids" },
  { signal: "keyword", weight: 2.0, why: "overlapping terms in the content" },
  { signal: "recency", weight: 1.0, why: "newer records edge out older ones" },
  { signal: "outcome", weight: 0.75, why: "runs that succeeded rank above runs that did not" },
  { signal: "semantic kind", weight: 0.5, why: "durable facts over one-off episodes" },
];

export default function MemoryPage() {
  const [overview, setOverview] = useState<MemoryOverview | null>(null);
  const [namespace, setNamespace] = useState<string>("");
  const [query, setQuery] = useState("retry");
  const [results, setResults] = useState<MemoryRecord[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    memoryOverview()
      .then((o) => {
        setOverview(o);
        const first = Object.keys(o.namespaces)[0];
        if (first) setNamespace(first);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const search = useCallback(async () => {
    if (!query.trim() || !namespace) return;
    setSearching(true);
    setError(null);
    try {
      setResults((await searchMemory(query, namespace, 20)).results);
    } catch (e) {
      setError(e);
      setResults(null);
    } finally {
      setSearching(false);
    }
  }, [query, namespace]);

  if (loading) return <Loading label="Loading memory…" />;

  const namespaces = Object.entries(overview?.namespaces || {});

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={Brain}
        title="Agent Memory"
        subtitle="What agents remembered across runs, and how recall ranks it"
        gradient="from-fuchsia-500/10 via-violet-500/5"
        iconGradient="from-fuchsia-500 to-violet-500"
        border="border-fuchsia-500/20"
        note={
          <>
            Records are written at the end of a run and recalled at the start of the next
            one. Recall is hybrid and uses <strong>no embeddings</strong> — which keeps
            memory working offline and, more usefully, ranks exact identifiers above fuzzy
            similarity. Agents recall by file path far more often than by vibe.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <HowTo concept="memory" />

      {!namespaces.length && !error ? (
        <Empty
          icon={Brain}
          title="Nothing remembered yet"
          hint="Run a harness that declares a memory backend — records appear here afterwards."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Records" value={overview?.total ?? 0} />
            <Stat label="Namespaces" value={namespaces.length} hint="isolated per harness" />
            <Stat
              label="Backend"
              value="jsonl"
              hint="plain files, greppable, diffable in git"
            />
            <Stat label="Embeddings" value="none" hint="deterministic and offline" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6">
            {/* -------------------------------------------- namespaces */}
            <div className="space-y-3">
              <p className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5" />
                Namespaces
              </p>
              {namespaces.map(([name, ns]) => (
                <Card
                  key={name}
                  onClick={() => setNamespace(name)}
                  className={`cursor-pointer transition-all ${
                    namespace === name
                      ? "border-fuchsia-500/50 bg-fuchsia-500/5"
                      : "hover:border-border/80"
                  }`}
                >
                  <CardContent className="p-4 space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-semibold text-sm font-mono truncate">{name}</p>
                      <Badge variant="outline" className="text-[10px] shrink-0">
                        {ns.records}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(ns.kinds).map(([k, n]) => (
                        <span
                          key={k}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono"
                        >
                          {k} · {n}
                        </span>
                      ))}
                    </div>
                    {ns.newest && (
                      <p className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        newest {new Date(ns.newest).toLocaleString()}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}

              <Card className="bg-muted/30">
                <CardContent className="p-4 space-y-2">
                  <p className="text-[11px] font-semibold flex items-center gap-1.5">
                    <Database className="h-3.5 w-3.5" />
                    Recall weights
                  </p>
                  {WEIGHTS.map((w) => (
                    <div key={w.signal} className="space-y-0.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-mono">{w.signal}</span>
                        <span className="text-muted-foreground">×{w.weight}</span>
                      </div>
                      <div className="h-1 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full bg-fuchsia-500/60"
                          style={{ width: `${(w.weight / 3) * 100}%` }}
                        />
                      </div>
                      <p className="text-[10px] text-muted-foreground">{w.why}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>

            {/* -------------------------------------------- search */}
            <div className="space-y-4">
              <Card>
                <CardContent className="p-5 flex gap-2">
                  <Input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && search()}
                    placeholder="Search memory — try a file path or tool name"
                  />
                  <Button onClick={search} disabled={searching || !query.trim()} className="gap-2 shrink-0">
                    <Search className={`h-4 w-4 ${searching ? "animate-pulse" : ""}`} />
                    Recall
                  </Button>
                </CardContent>
              </Card>

              {results !== null && (
                <>
                  <p className="text-xs text-muted-foreground">
                    {results.length} result{results.length === 1 ? "" : "s"} in{" "}
                    <code className="font-mono">{namespace}</code>
                    {results.length > 0 && " — ordered by hybrid score, highest first"}
                  </p>
                  {results.length === 0 ? (
                    <Empty
                      icon={Search}
                      title="Nothing recalled for that query"
                      hint="Recall is exact-match weighted — try a tool name or a path that appeared in a run."
                    />
                  ) : (
                    <div className="space-y-2">
                      {results.map((r) => (
                        <RecordCard key={r.id} record={r} />
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function RecordCard({ record }: { record: MemoryRecord }) {
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px]">
              {record.kind}
            </Badge>
            {record.outcome && (
              <span
                className={`text-[10px] font-medium ${
                  record.outcome === "completed" ? "text-emerald-400" : "text-amber-400"
                }`}
              >
                {record.outcome}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            {record.score != null && (
              <span className="font-mono">score {record.score.toFixed(2)}</span>
            )}
            <span>{new Date(record.created_at).toLocaleString()}</span>
          </div>
        </div>

        <p className="text-xs whitespace-pre-wrap leading-relaxed">{record.content}</p>

        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {record.entities?.map((e) => (
            <span
              key={e}
              title="entity — weighted highest in recall"
              className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-fuchsia-500/10 text-fuchsia-400 border border-fuchsia-500/20 font-mono"
            >
              <Link2 className="h-2.5 w-2.5" />
              {e}
            </span>
          ))}
          {record.tags?.map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
            >
              <Tag className="h-2.5 w-2.5" />
              {t}
            </span>
          ))}
        </div>

        {record.source_id && (
          <p className="text-[10px] font-mono text-muted-foreground border-t border-border pt-2">
            from {record.source_id}
            {record.source_run_id && ` · run ${shortId(record.source_run_id)}`}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

"use client";

/**
 * The spec, browsable.
 *
 * PromptFile v1 is the thing this project asks other tools to adopt, so it should be
 * readable without cloning the repo or opening a JSON schema in a text editor. The schema
 * is served by the API rather than duplicated here — a spec page that drifts from the spec
 * it documents is worse than no spec page.
 *
 * The plugin inventory sits alongside it because the two answer the same question from
 * opposite ends: what the format allows, and what this installation can actually do.
 */

import React, { useEffect, useState } from "react";
import {
  FileCode2, ChevronRight, Puzzle, CheckCircle2, XCircle, ExternalLink,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorPanel, Loading, PageHeader } from "@/components/v1/shell";
import { JsonSchema, PluginEntry, SchemaProperty, plugins, spec } from "@/lib/v1";

const GROUP_BLURB: Record<string, string> = {
  "assay.renderers": "Turn a template into messages",
  "assay.providers": "Talk to a model",
  "assay.evaluators": "Decide whether a run passed",
  "assay.guardrails": "Inspect input and output for risk",
  "assay.stores": "Where artifacts live",
  "assay.tools": "What an agent can call",
  "assay.context": "Decide what stays in context",
  "assay.controllers": "Allow, deny or alter a tool call",
  "assay.memory": "What carries between runs",
};

export default function SpecPage() {
  const [schema, setSchema] = useState<JsonSchema | null>(null);
  const [inventory, setInventory] = useState<Record<string, PluginEntry[]> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"schema" | "plugins">("schema");

  useEffect(() => {
    Promise.all([spec(), plugins()])
      .then(([s, p]) => {
        setSchema(s);
        setInventory(p);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loading label="Loading the spec…" />;

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={FileCode2}
        title="PromptFile v1"
        subtitle={schema?.description || "The open artifact format"}
        gradient="from-blue-500/10 via-indigo-500/5"
        iconGradient="from-blue-500 to-indigo-500"
        border="border-blue-500/20"
        note={
          <>
            Served live from the API, so this page cannot drift from the schema the engine
            validates against. Two conformance rules do most of the work: readers{" "}
            <strong>MUST</strong> refuse a major version they do not implement, and writers{" "}
            <strong>MUST</strong> preserve fields they do not understand. Together those
            are what let a file written today survive a tool written in five years.
          </>
        }
        action={
          <a
            href="/api/assay/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            OpenAPI <ExternalLink className="h-3 w-3" />
          </a>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <div className="flex gap-2">
        {(["schema", "plugins"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              tab === t
                ? "bg-blue-500/10 text-blue-400 border border-blue-500/30"
                : "text-muted-foreground hover:text-foreground border border-transparent"
            }`}
          >
            {t === "schema" ? "Schema" : "Installed plugins"}
          </button>
        ))}
      </div>

      {tab === "schema" && schema && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Required: {(schema.required || []).map((r) => (
              <code key={r} className="font-mono mx-1 px-1 py-0.5 rounded bg-muted">
                {r}
              </code>
            ))}
            — everything else is optional, and unknown keys are preserved rather than
            rejected.
          </p>
          {Object.entries(schema.properties || {}).map(([name, prop]) => (
            <PropertyRow
              key={name}
              name={name}
              prop={prop}
              required={(schema.required || []).includes(name)}
            />
          ))}
        </div>
      )}

      {tab === "plugins" && inventory && (
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Nine extension points, all discovered through entry points. Adding a capability
            means shipping a package, not patching this one — which is the whole reason the
            core is small.
          </p>
          {Object.entries(inventory).map(([group, entries]) => (
            <Card key={group}>
              <CardContent className="p-5 space-y-3">
                <div className="flex items-baseline gap-3 flex-wrap">
                  <p className="text-sm font-semibold font-mono flex items-center gap-2">
                    <Puzzle className="h-4 w-4 text-blue-400" />
                    {group}
                  </p>
                  <span className="text-xs text-muted-foreground">
                    {GROUP_BLURB[group] || ""}
                  </span>
                  <Badge variant="outline" className="text-[10px] ml-auto">
                    {entries.length}
                  </Badge>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {entries.map((e) => (
                    <div
                      key={e.name}
                      className={`rounded-lg border p-3 ${
                        e.error ? "border-red-500/30 bg-red-500/5" : "border-border bg-muted/30"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {e.error ? (
                          <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
                        ) : (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                        )}
                        <span className="text-xs font-semibold font-mono">{e.name}</span>
                        {e.distribution && (
                          <span className="text-[10px] text-muted-foreground ml-auto">
                            {e.distribution}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] font-mono text-muted-foreground mt-1 truncate">
                        {e.target}
                      </p>
                      {e.error && (
                        <p className="text-[10px] text-red-400 mt-1">{e.error}</p>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function PropertyRow({
  name,
  prop,
  required,
  depth = 0,
}: {
  name: string;
  prop: SchemaProperty;
  required?: boolean;
  depth?: number;
}) {
  const [open, setOpen] = useState(false);
  const children = prop.properties || prop.items?.properties;
  const expandable = !!children && Object.keys(children).length > 0;

  return (
    <Card className={depth ? "border-border/50" : ""}>
      <CardContent
        className={`p-4 ${expandable ? "cursor-pointer" : ""}`}
        onClick={() => expandable && setOpen(!open)}
      >
        <div className="flex items-start gap-2">
          {expandable ? (
            <ChevronRight
              className={`h-4 w-4 mt-0.5 shrink-0 text-muted-foreground transition-transform ${
                open ? "rotate-90" : ""
              }`}
            />
          ) : (
            <span className="w-4 shrink-0" />
          )}
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <code className="text-sm font-mono font-semibold">{name}</code>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
                {Array.isArray(prop.type) ? prop.type.join(" | ") : prop.type || "any"}
              </span>
              {required && (
                <Badge variant="outline" className="text-[10px] text-blue-400 border-blue-500/40">
                  required
                </Badge>
              )}
              {prop.const !== undefined && (
                <span className="text-[10px] font-mono text-muted-foreground">
                  = {JSON.stringify(prop.const)}
                </span>
              )}
            </div>
            {prop.description && (
              <p className="text-xs text-muted-foreground leading-relaxed">
                {prop.description}
              </p>
            )}
            {prop.enum && (
              <div className="flex flex-wrap gap-1 pt-0.5">
                {prop.enum.map((v) => (
                  <span
                    key={String(v)}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono"
                  >
                    {String(v)}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {open && children && (
          <div className="mt-3 ml-6 space-y-2">
            {Object.entries(children).map(([k, v]) => (
              <PropertyRow key={k} name={k} prop={v} depth={depth + 1} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

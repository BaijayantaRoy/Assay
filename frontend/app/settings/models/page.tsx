"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Cpu, Database, RefreshCw, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { modelCatalogue, syncModels, type ModelCatalogue } from "@/lib/v1";

export default function ModelsSettingsPage() {
  const [catalogue, setCatalogue] = useState<ModelCatalogue | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    modelCatalogue()
      .then(setCatalogue)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  async function sync() {
    setSyncing(true);
    setError(null);
    setMessage(null);
    try {
      const result = await syncModels();
      setMessage(`Synced ${result.synced} models across ${result.providers} providers via ${result.source}.`);
      setCatalogue(await modelCatalogue());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Model sync failed");
    } finally {
      setSyncing(false);
    }
  }

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!catalogue || !needle) return catalogue?.models ?? [];
    return catalogue.models.filter(model =>
      [model.ref, model.name, model.provider, ...model.capabilities]
        .some(value => value.toLowerCase().includes(needle)),
    );
  }, [catalogue, query]);

  return (
    <div className="space-y-6 max-w-6xl animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Database className="h-6 w-6 text-primary" /> Global Model Catalogue
          </h1>
          <p className="text-muted-foreground mt-1">Searchable metadata used by stable PromptFile model bindings.</p>
        </div>
        <Button onClick={sync} disabled={syncing} className="gap-2">
          <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
          {syncing ? "Syncing…" : "Sync now"}
        </Button>
      </div>

      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">{error}</div>}
      {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-400 flex items-center gap-2"><CheckCircle2 className="h-4 w-4" />{message}</div>}

      {loading ? (
        <Card><CardContent className="p-8 text-sm text-muted-foreground">Reading catalogue…</CardContent></Card>
      ) : catalogue && (
        <>
          <Card className={catalogue.is_seed ? "border-amber-500/40 bg-amber-500/5" : ""}>
            <CardContent className="p-5 flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="font-semibold flex items-center gap-2">
                  {catalogue.is_seed && <AlertTriangle className="h-4 w-4 text-amber-500" />}
                  {catalogue.count} models · {catalogue.providers.length} providers
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {catalogue.is_seed
                    ? "Bundled seed data — not yet synced; metadata may be stale."
                    : `Synced ${catalogue.synced_at ? new Date(catalogue.synced_at).toLocaleString() : "at an unknown time"} from ${catalogue.source ?? "configured sources"}.`}
                </p>
              </div>
              <div className="relative min-w-[240px] flex-1 max-w-md">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search model, provider, or capability…" className="pl-9" />
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {visible.map(model => (
              <Card key={model.ref} className={model.deprecated ? "opacity-60" : ""}>
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-start gap-2">
                    <Cpu className="h-4 w-4 text-primary mt-0.5" />
                    <div className="min-w-0">
                      <p className="font-semibold truncate">{model.name}</p>
                      <code className="text-[10px] text-muted-foreground">{model.ref}</code>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <span className="text-muted-foreground">Context</span><span className="text-right">{model.context_window.toLocaleString()}</span>
                    <span className="text-muted-foreground">Max output</span><span className="text-right">{model.max_output_tokens.toLocaleString()}</span>
                    <span className="text-muted-foreground">Input / MTok</span><span className="text-right">${model.input_cost_per_mtok.toFixed(2)}</span>
                    <span className="text-muted-foreground">Output / MTok</span><span className="text-right">${model.output_cost_per_mtok.toFixed(2)}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {model.capabilities.map(capability => <span key={capability} className="rounded bg-muted px-1.5 py-0.5 text-[9px] text-muted-foreground">{capability}</span>)}
                    {model.deprecated && <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[9px] text-red-400">deprecated</span>}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          {visible.length === 0 && <p className="py-12 text-center text-sm text-muted-foreground">No models match that filter.</p>}
        </>
      )}
    </div>
  );
}

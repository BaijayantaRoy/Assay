"use client";

/**
 * One PromptFile — read, rendered, evaluated, and lightly edited.
 *
 * This replaces the old detail view's per-version editor with something narrower on
 * purpose: the source of truth is the file on disk, and `body` is the one field this page
 * writes back through `/v1` (a PATCH bumps the version and stamps provenance — see
 * `PromptFile.bump()`). Frontmatter fields like model, tags, status, guardrails, and evals
 * remain source-file/CLI work until there is a dedicated editor; duplicating a partial
 * frontmatter form here would be a second, easier-to-drift way to do the same edit.
 *
 * The id is a route catch-all (`[...id]`) rather than a single segment because `/v1`
 * prompt ids are path-like — `agents/code-reviewer` — and a single dynamic segment cannot
 * hold a slash.
 */

import React, { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, ArrowLeft, Check, Clock, FileText, Play, Save, TestTube2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ErrorPanel, Loading, VerifiedMark } from "@/components/v1/shell";
import {
  EvalReport, PromptDetail, PromptHistoryEntry, RenderResult,
  evaluatePrompt, getPrompt, promptHistory, renderPrompt, updatePrompt,
} from "@/lib/v1";
import { useToast } from "@/components/toast-provider";

export default function Client({ params }: { params: Promise<{ id: string[] }> }) {
  const { id: idParts } = use(params);
  const id = (idParts || []).join("/");
  const { toast } = useToast();

  const [detail, setDetail] = useState<PromptDetail | null>(null);
  const [history, setHistory] = useState<PromptHistoryEntry[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);

  const [variables, setVariables] = useState<Record<string, string>>({});
  const [rendered, setRendered] = useState<RenderResult | null>(null);
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState<unknown>(null);

  const [evalReport, setEvalReport] = useState<EvalReport | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evalError, setEvalError] = useState<unknown>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([getPrompt(id), promptHistory(id).catch(() => ({ id, history: [] }))])
      .then(([d, h]) => {
        setDetail(d);
        setBody(String(d.document.body ?? ""));
        setHistory(h.history || []);
        setVariables(Object.fromEntries(d.variables.map((v) => [v, ""])));
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [id]);

  const dirty = detail ? body !== String(detail.document.body ?? "") : false;

  const save = async () => {
    if (!detail) return;
    setSaving(true);
    try {
      const updated = await updatePrompt(id, { body, commit_message: "Edited from All Prompts" });
      const fresh = await getPrompt(id);
      setDetail(fresh);
      setBody(String(fresh.document.body ?? ""));
      toast(`Saved — now version ${updated.version}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const render = async () => {
    setRendering(true);
    setRenderError(null);
    try {
      setRendered(await renderPrompt(id, variables));
    } catch (e) {
      setRenderError(e);
    } finally {
      setRendering(false);
    }
  };

  const runEvals = async () => {
    setEvaluating(true);
    setEvalError(null);
    try {
      setEvalReport(await evaluatePrompt(id));
    } catch (e) {
      setEvalError(e);
    } finally {
      setEvaluating(false);
    }
  };

  if (loading) return <Loading label={`Loading ${id}…`} />;
  if (error != null) return <ErrorPanel error={error} />;
  if (!detail) return null;

  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/prompts"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> All Prompts
      </Link>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold">{detail.name || detail.id}</h1>
            <Badge variant="secondary">{detail.kind}</Badge>
            <Badge variant="outline">{detail.status}</Badge>
            <span className="text-xs text-muted-foreground">v{detail.version}</span>
          </div>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{detail.id}</p>
          {detail.description && (
            <p className="mt-2 text-sm text-muted-foreground max-w-2xl">{detail.description}</p>
          )}
          <div className="mt-2 flex gap-1.5 flex-wrap">
            {detail.tags.map((t) => (
              <Badge key={t} variant="secondary" className="text-[10px] px-1.5 py-0">{t}</Badge>
            ))}
            {detail.model && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 font-mono">{detail.model}</Badge>
            )}
          </div>
        </div>
      </div>

      {/* Body editor */}
      <Card>
        <CardContent className="p-5 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" /> Body
            </p>
            <Button size="sm" onClick={save} disabled={!dirty || saving} className="gap-1.5">
              <Save className="h-3.5 w-3.5" /> {saving ? "Saving…" : dirty ? "Save (bumps version)" : "Saved"}
            </Button>
          </div>
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={10}
            className="font-mono text-xs"
          />
          <p className="text-[11px] text-muted-foreground">
            Only the body is editable here. Model, tags, status, guardrails, and evals live in
            frontmatter — edit them in the source PromptFile under <code className="font-mono">prompts/</code> or through the CLI.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Render */}
        <Card>
          <CardContent className="p-5 space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
              <Play className="h-3.5 w-3.5" /> Render — no model call
            </p>
            {detail.variables.length === 0 ? (
              <p className="text-xs text-muted-foreground">This prompt takes no variables.</p>
            ) : (
              <div className="space-y-2">
                {detail.variables.map((v) => (
                  <div key={v} className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-muted-foreground w-28 shrink-0 truncate">{v}</span>
                    <input
                      className="flex-1 rounded-md border bg-background px-2 py-1 text-xs"
                      value={variables[v] ?? ""}
                      onChange={(e) => setVariables((prev) => ({ ...prev, [v]: e.target.value }))}
                    />
                  </div>
                ))}
              </div>
            )}
            <Button size="sm" onClick={render} disabled={rendering} className="gap-1.5">
              <Play className="h-3.5 w-3.5" /> {rendering ? "Rendering…" : "Render"}
            </Button>
            {renderError != null && <ErrorPanel error={renderError} />}
            {rendered && (
              <div className="rounded-lg border bg-muted/30 p-3 space-y-2 max-h-64 overflow-y-auto">
                {rendered.messages.map((m, i) => (
                  <div key={i} className="text-xs">
                    <p className="font-semibold text-muted-foreground uppercase text-[10px]">{m.role}</p>
                    <p className="whitespace-pre-wrap font-mono">{m.content}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Evaluate */}
        <Card>
          <CardContent className="p-5 space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
              <TestTube2 className="h-3.5 w-3.5" /> Eval cases
            </p>
            {!detail.has_evals ? (
              <div className="flex items-start gap-2 text-xs text-amber-500">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <p>
                  No eval cases attached. This artifact passes every run by default — that is
                  not the same as working. Add at least one in the source PromptFile, then run
                  <code className="font-mono"> assay test {id}</code> or return here.
                </p>
              </div>
            ) : (
              <>
                <Button size="sm" onClick={runEvals} disabled={evaluating} className="gap-1.5">
                  <Check className="h-3.5 w-3.5" /> {evaluating ? "Running…" : "Run evals"}
                </Button>
                {evalError != null && <ErrorPanel error={evalError} />}
                {evalReport && (
                  <div className="space-y-2">
                    <VerifiedMark verified={evalReport.passed} />
                    {evalReport.cases?.map((c) => (
                      <div key={c.id} className="flex items-center justify-between text-xs rounded-lg border px-3 py-1.5">
                        <span className="font-mono">{c.id}</span>
                        <VerifiedMark verified={c.passed} />
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* History */}
      <Card>
        <CardContent className="p-5 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" /> History
          </p>
          {history.length === 0 ? (
            <p className="text-xs text-muted-foreground">No prior versions recorded.</p>
          ) : (
            <div className="space-y-1.5">
              {history.map((h, i) => (
                <div key={i} className="flex items-center justify-between text-xs rounded-lg border px-3 py-1.5">
                  <span>{h.message || "—"}</span>
                  <span className="text-muted-foreground">
                    {h.version != null ? `v${h.version}` : ""} {h.timestamp ? `· ${h.timestamp}` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

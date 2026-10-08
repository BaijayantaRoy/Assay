"use client";

/**
 * Integrations — how the rest of the toolchain finds these prompts.
 *
 * Three answers to the same question, arranged from broadest to deepest.
 *
 * **AGENTS.md** reaches the most tools for the least effort: one generated file read
 * natively by fourteen coding agents. **MCP** reaches fewer but goes further — an agent
 * can search, run and test, not merely know the prompts exist. **Chatbot export** reaches
 * everyone, including people who never open an IDE, and is the shallowest: a paste carries
 * the text and nothing else.
 *
 * Preview before write, everywhere. Writing AGENTS.md touches a file in the user's
 * repository, and a button that does that without showing what it will write first is a
 * button people learn not to press.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  Plug, FileCode2, Terminal, Database, Download, RefreshCw, MessageSquare,
  CheckCircle2, ExternalLink, AlertTriangle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorPanel, Loading, PageHeader } from "@/components/v1/shell";
import { CommandRow } from "@/components/v1/howto";
import {
  AgentsMdPreview, Bundle, ChatExport, McpConfig, ModelCatalogue, PromptSummary,
  exportForChat, listBundles, listPrompts, mcpConfig, modelCatalogue,
  previewAgentsMd, syncModels, writeAgentsMd,
} from "@/lib/v1";

type Tab = "agents" | "mcp" | "chat" | "models";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "agents", label: "Coding agents", icon: FileCode2 },
  { id: "mcp", label: "MCP", icon: Terminal },
  { id: "chat", label: "Chatbots", icon: MessageSquare },
  { id: "models", label: "Model catalogue", icon: Database },
];

export default function IntegrationsPage() {
  const [tab, setTab] = useState<Tab>("agents");
  const [error, setError] = useState<unknown>(null);

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon={Plug}
        title="Integrations"
        subtitle="How your editor, your agents and your chatbots find these prompts"
        gradient="from-sky-500/10 via-cyan-500/5"
        iconGradient="from-sky-500 to-cyan-500"
        border="border-sky-500/20"
        note={
          <>
            Three routes, broadest first. <strong>AGENTS.md</strong> is one generated file
            read natively by fourteen coding agents. <strong>MCP</strong> reaches fewer
            tools but goes deeper — an agent can search, run and test, not just know the
            prompts exist. <strong>Export</strong> reaches everyone, and carries the least:
            a paste is text, without the guardrails or evals.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <div className="flex gap-2 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              tab === t.id
                ? "bg-sky-500/10 text-sky-400 border-sky-500/30"
                : "text-muted-foreground border-transparent hover:text-foreground"
            }`}
          >
            <t.icon className="h-3.5 w-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {tab === "agents" && <AgentsPanel onError={setError} />}
      {tab === "mcp" && <McpPanel onError={setError} />}
      {tab === "chat" && <ChatPanel onError={setError} />}
      {tab === "models" && <ModelsPanel onError={setError} />}
    </div>
  );
}

// ---------------------------------------------------------------------------

function AgentsPanel({ onError }: { onError: (e: unknown) => void }) {
  const [preview, setPreview] = useState<AgentsMdPreview | null>(null);
  const [targets, setTargets] = useState<string[]>(["agents"]);
  const [written, setWritten] = useState<{ file: string; created: boolean }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    previewAgentsMd().then(setPreview).catch(onError).finally(() => setLoading(false));
  }, [onError]);

  useEffect(() => { load(); }, [load]);

  const write = async () => {
    setBusy(true);
    try {
      const result = await writeAgentsMd(targets);
      setWritten(result.written);
      load();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  };

  const toggle = (t: string) =>
    setTargets((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));

  if (loading) return <Loading label="Building the index…" />;
  if (!preview) return null;

  return (
    <div className="space-y-4">
      <Card className="border-sky-500/30 bg-sky-500/5">
        <CardContent className="p-5 space-y-3">
          <p className="text-sm font-semibold">
            One file, {preview.reaches.length} tools
          </p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            AGENTS.md is stewarded by the Agentic AI Foundation under the Linux Foundation
            and appears in 60,000+ repositories. Writing it means every agent below can see
            your {preview.artifacts} artifacts, what inputs they take, and the command that
            runs them — without you telling each tool separately.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {preview.reaches.map((tool) => (
              <span
                key={tool}
                className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
              >
                {tool}
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5 space-y-4">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex flex-wrap gap-2">
              {Object.entries(preview.targets).map(([key, t]) => (
                <button
                  key={key}
                  onClick={() => toggle(key)}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs border transition-colors ${
                    targets.includes(key)
                      ? "bg-sky-500/10 text-sky-400 border-sky-500/30"
                      : "text-muted-foreground border-border hover:text-foreground"
                  }`}
                >
                  <code className="font-mono">{t.file}</code>
                  {t.exists && (
                    <Badge variant="outline" className="text-[9px] px-1 py-0">
                      {t.has_generated_block ? "refresh" : "append"}
                    </Badge>
                  )}
                </button>
              ))}
            </div>
            <Button onClick={write} disabled={busy || !targets.length} className="gap-2">
              <Download className={`h-4 w-4 ${busy ? "animate-pulse" : ""}`} />
              {busy ? "Writing…" : `Write ${targets.length} file${targets.length === 1 ? "" : "s"}`}
            </Button>
          </div>

          <p className="text-[11px] text-muted-foreground">{preview.note}</p>

          {written && (
            <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-emerald-400">
                  {written.map((w) => `${w.created ? "Created" : "Updated"} ${w.file}`).join(" · ")}
                </p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Coding agents that read these files will now find your prompts. Re-run
                  after adding or removing artifacts.
                </p>
              </div>
            </div>
          )}

          <CommandRow command="assay agents init" does="same thing from the terminal" />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5 space-y-2">
          <p className="text-sm font-semibold">Preview</p>
          <pre className="text-[10px] font-mono whitespace-pre-wrap bg-muted/50 rounded p-3 max-h-[420px] overflow-auto">
            {preview.content}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------

function McpPanel({ onError }: { onError: (e: unknown) => void }) {
  const [config, setConfig] = useState<McpConfig | null>(null);
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([mcpConfig(), listBundles()])
      .then(([c, b]) => {
        setConfig(c);
        setBundles(b.bundles);
      })
      .catch(onError)
      .finally(() => setLoading(false));
  }, [onError]);

  if (loading) return <Loading label="Building config…" />;
  if (!config) return null;

  return (
    <div className="space-y-4">
      <Card className="border-sky-500/30 bg-sky-500/5">
        <CardContent className="p-5 space-y-2">
          <p className="text-sm font-semibold">Live access, not just awareness</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{config.note}</p>
          <p className="text-[11px] font-mono text-muted-foreground break-all pt-1">
            workspace: {config.workspace_root}
          </p>
        </CardContent>
      </Card>

      {bundles.map((bundle) => (
        <Card key={bundle.id} className="border-violet-500/30">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <p className="text-sm font-semibold">{bundle.name}</p>
                <p className="text-[11px] text-muted-foreground">
                  {bundle.kind} · ships in{" "}
                  <code className="font-mono">{bundle.path}</code>
                </p>
              </div>
              {bundle.skills.length > 0 && (
                <Badge variant="outline" className="text-[10px] text-violet-400 border-violet-500/40">
                  {bundle.skills.length} skill{bundle.skills.length === 1 ? "" : "s"}
                </Badge>
              )}
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed">{bundle.summary}</p>

            <div className="rounded-lg border border-border bg-muted/30 p-3">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5">
                Why this and not just AGENTS.md
              </p>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{bundle.why}</p>
            </div>

            <div className="space-y-1.5">
              {bundle.install.map((cmd) => (
                <CommandRow key={cmd} command={cmd} />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {config.clients.map((client) => (
          <Card key={client.id}>
            <CardContent className="p-5 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold">{client.name}</p>
                <a
                  href={client.docs}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
                >
                  docs <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Paste into <code className="font-mono">{client.file}</code>
              </p>
              <CopyBlock text={client.config} />
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardContent className="p-5 space-y-3">
          <p className="text-sm font-semibold">What the agent gets</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {config.tools.map((t) => (
              <div key={t.name} className="flex items-center gap-2 text-xs">
                <code className="font-mono text-sky-400">{t.name}</code>
                <span className="text-muted-foreground">— {t.does}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------

function ModelsPanel({ onError }: { onError: (e: unknown) => void }) {
  const [cat, setCat] = useState<ModelCatalogue | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const load = useCallback(() => {
    modelCatalogue().then(setCat).catch(onError).finally(() => setLoading(false));
  }, [onError]);

  useEffect(() => { load(); }, [load]);

  const sync = async () => {
    setSyncing(true);
    setResult(null);
    try {
      const r = await syncModels();
      setResult(`Synced ${r.synced} models from ${r.providers} providers via ${r.source}`);
      load();
    } catch (e) {
      onError(e);
    } finally {
      setSyncing(false);
    }
  };

  if (loading) return <Loading label="Reading the catalogue…" />;
  if (!cat) return null;

  const visible = cat.models.filter((m) =>
    !query.trim() ? true : m.ref.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <div className="space-y-4">
      <Card className={cat.is_seed ? "border-amber-500/40 bg-amber-500/5" : ""}>
        <CardContent className="p-5 space-y-3">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="space-y-1">
              <p className="text-sm font-semibold flex items-center gap-2">
                {cat.is_seed && <AlertTriangle className="h-4 w-4 text-amber-400" />}
                {cat.count} models · {cat.providers.length} providers
              </p>
              <p className="text-xs text-muted-foreground">
                {cat.is_seed ? (
                  <>
                    This is the small bundled seed — the catalogue has never been synced.
                    Prices and context windows move constantly, so anything here may be
                    out of date.
                  </>
                ) : (
                  <>
                    Last synced {cat.synced_at && new Date(cat.synced_at).toLocaleString()}{" "}
                    from <code className="font-mono">{cat.source}</code>
                  </>
                )}
              </p>
            </div>
            <Button onClick={sync} disabled={syncing} className="gap-2">
              <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
              {syncing ? "Syncing…" : "Sync now"}
            </Button>
          </div>

          {result && (
            <p className="text-xs text-emerald-400 flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {result}
            </p>
          )}

          <p className="text-[11px] text-muted-foreground border-t border-border pt-3">
            Tries <code className="font-mono">models.dev</code> first — an MIT-licensed
            open database covering 75+ providers, contributed by pull request — then falls
            back to <code className="font-mono">openrouter.ai</code>, which knows what is
            servable today. Nothing in the engine hardcodes pricing; the catalogue is
            plain data, so a vendor changing prices never requires a release.
          </p>

          <CommandRow command="assay models sync" does="same thing from the terminal" />
        </CardContent>
      </Card>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Filter models…"
        className="w-full h-9 rounded-md border border-border bg-background px-3 text-xs"
      />

      <Card>
        <CardContent className="p-0 overflow-auto max-h-[540px]">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-background border-b border-border">
              <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-2.5">model</th>
                <th className="px-4 py-2.5 text-right">context</th>
                <th className="px-4 py-2.5 text-right">$/M in</th>
                <th className="px-4 py-2.5 text-right">$/M out</th>
                <th className="px-4 py-2.5">capabilities</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((m) => (
                <tr key={m.ref} className="border-b border-border/50 hover:bg-muted/30">
                  <td className="px-4 py-2 font-mono">{m.ref}</td>
                  <td className="px-4 py-2 text-right text-muted-foreground">
                    {m.context_window ? m.context_window.toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-2 text-right text-muted-foreground">
                    {m.input_cost_per_mtok ? `$${m.input_cost_per_mtok.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-4 py-2 text-right text-muted-foreground">
                    {m.output_cost_per_mtok ? `$${m.output_cost_per_mtok.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-4 py-2">
                    <span className="text-[10px] text-muted-foreground">
                      {m.capabilities.join(", ") || "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visible.length === 0 && (
            <p className="p-8 text-center text-xs text-muted-foreground">
              Nothing matches that filter.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------

/**
 * Chatbot export — the shallowest integration, and the most used.
 *
 * Not everyone is in an IDE. This renders a prompt with its variables filled and hands
 * back text to paste into ChatGPT, Claude or Gemini.
 *
 * The caveat is stated on the page rather than buried: a paste carries the text and
 * nothing else. Guardrails, eval cases and the model binding are part of the PromptFile
 * and do not travel. Someone who pastes a prompt tuned at temperature 0 into a chat
 * window and gets different output should know why before they go looking for a bug.
 */
function ChatPanel({ onError }: { onError: (e: unknown) => void }) {
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ChatExport | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [withSettings, setWithSettings] = useState(true);

  useEffect(() => {
    listPrompts()
      .then((p) => {
        // Harnesses and loops are not pasteable — they are execution shapes, not text.
        const pasteable = p.filter((x) => x.kind !== "harness" && x.kind !== "loop");
        setPrompts(pasteable);
        if (pasteable.length) setSelected(pasteable[0].id);
      })
      .catch(onError)
      .finally(() => setLoading(false));
  }, [onError]);

  const current = prompts.find((p) => p.id === selected);

  // A different prompt starts with empty inputs and no stale export. Adjusting state
  // during render (not in an effect) avoids a second, cascading render.
  const [shownFor, setShownFor] = useState(selected);
  if (shownFor !== selected) {
    setShownFor(selected);
    setValues({});
    setResult(null);
  }

  const render = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      setResult(await exportForChat(selected, values));
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Loading label="Loading prompts…" />;

  const text = result ? (withSettings ? result.with_settings : result.plain) : "";

  return (
    <div className="space-y-4">
      <Card className="border-sky-500/30 bg-sky-500/5">
        <CardContent className="p-5 space-y-2">
          <p className="text-sm font-semibold">Fill it in, copy it, paste it anywhere</p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            No model is called and nothing is spent — this only renders the template. It
            works for anyone on a chat interface rather than an editor, which is most
            people most of the time.
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-6">
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Prompt</label>
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                className="w-full h-9 rounded-md border border-border bg-background px-2 text-xs"
              >
                {prompts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.id}
                  </option>
                ))}
              </select>
              {current?.description && (
                <p className="text-[11px] text-muted-foreground">{current.description}</p>
              )}
            </div>

            {current && current.variables.length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Variables</p>
                {current.variables.map((v) => (
                  <div key={v} className="space-y-1">
                    <label className="text-[11px] font-mono text-muted-foreground">{v}</label>
                    <textarea
                      value={values[v] ?? ""}
                      onChange={(e) => setValues((s) => ({ ...s, [v]: e.target.value }))}
                      placeholder={`value for ${v}`}
                      rows={2}
                      className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs resize-y"
                    />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                This prompt takes no variables.
              </p>
            )}

            <label className="flex items-center gap-2 text-[11px] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={withSettings}
                onChange={(e) => setWithSettings(e.target.checked)}
                className="accent-sky-500"
              />
              Append the model and parameters it was designed against
            </label>

            <Button onClick={render} disabled={busy || !selected} className="w-full gap-2">
              <MessageSquare className={`h-4 w-4 ${busy ? "animate-pulse" : ""}`} />
              {busy ? "Rendering…" : "Render for chat"}
            </Button>

            {current && (
              <CommandRow
                command={`assay render ${current.id}${current.variables
                  .map((v) => ` -v ${v}=…`)
                  .join("")}`}
                does="from the terminal"
              />
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          {!result ? (
            <Card className="border-dashed">
              <CardContent className="p-10 text-center space-y-2">
                <MessageSquare className="h-8 w-8 mx-auto text-muted-foreground/40" />
                <p className="text-sm text-muted-foreground">
                  Fill in the variables and render to get copy-ready text.
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              <Card>
                <CardContent className="p-5 space-y-3">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <p className="text-sm font-semibold">
                      {text.length.toLocaleString()} characters
                    </p>
                    <div className="flex items-center gap-2">
                      {result.targets.map((t) => (
                        <a
                          key={t.id}
                          href={t.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-border hover:bg-muted"
                        >
                          {t.name} <ExternalLink className="h-3 w-3" />
                        </a>
                      ))}
                    </div>
                  </div>
                  <CopyBlock text={text} />
                  <p className="text-[11px] text-muted-foreground">{result.note}</p>
                </CardContent>
              </Card>

              {result.settings.length > 0 && withSettings && (
                <Card>
                  <CardContent className="p-5 space-y-1.5">
                    <p className="text-xs font-semibold">Appended notes</p>
                    {result.settings.map((s) => (
                      <p key={s} className="text-[11px] text-muted-foreground font-mono">
                        {s}
                      </p>
                    ))}
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function CopyBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — the text is still selectable on screen */
    }
  };
  return (
    <div className="relative">
      <pre className="text-[10px] font-mono whitespace-pre-wrap bg-muted/50 rounded p-3 max-h-56 overflow-auto">
        {text}
      </pre>
      <button
        onClick={copy}
        className="absolute top-2 right-2 px-2 py-1 rounded text-[10px] bg-background border border-border hover:bg-muted"
      >
        {copied ? "copied" : "copy"}
      </button>
    </div>
  );
}

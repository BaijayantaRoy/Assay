"use client";

import React, { useEffect, useMemo, useState } from "react";
import { FlaskConical, Play, SplitSquareHorizontal, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorPanel, Loading, PageHeader } from "@/components/v1/shell";
import {
  ExperimentResult,
  PromptSummary,
  compareExperiment,
  listPrompts,
} from "@/lib/v1";

export default function ABTestsPage() {
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [modelA, setModelA] = useState("");
  const [modelB, setModelB] = useState("");
  const [result, setResult] = useState<ExperimentResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    listPrompts()
      .then((items) => {
        setPrompts(items);
        const eligible = items.filter((item) => item.has_evals);
        setA(eligible[0]?.id || "");
        setB(eligible[1]?.id || eligible[0]?.id || "");
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const eligible = useMemo(() => prompts.filter((prompt) => prompt.has_evals), [prompts]);

  async function run() {
    if (!a || !b) return;
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      setResult(await compareExperiment(
        { prompt_id: a, model: modelA.trim() || undefined },
        { prompt_id: b, model: modelB.trim() || undefined },
      ));
    } catch (problem) {
      setError(problem);
    } finally {
      setRunning(false);
    }
  }

  if (loading) return <Loading label="Loading comparable PromptFiles…" />;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        icon={SplitSquareHorizontal}
        title="Paired A/B Comparison"
        subtitle="Compare two prompt or model variants on exactly the same declared eval cases."
        gradient="from-pink-500/10 via-rose-500/5"
        iconGradient="from-pink-500 to-rose-500"
        border="border-pink-500/20"
        note={
          <>
            Assay refuses variants whose resolved cases or assertions differ. The score
            delta is paired by case and bootstrapped at the case level. A winner is
            withheld unless the 95% delta interval excludes zero; fewer than three paired
            cases cannot establish one.
          </>
        }
      />

      {error != null && <ErrorPanel error={error} />}

      <Card>
        <CardContent className="p-5 space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <VariantPicker
              label="Variant A"
              prompts={eligible}
              prompt={a}
              model={modelA}
              setPrompt={setA}
              setModel={setModelA}
            />
            <VariantPicker
              label="Variant B"
              prompts={eligible}
              prompt={b}
              model={modelB}
              setPrompt={setB}
              setModel={setModelB}
            />
          </div>
          <Button onClick={run} disabled={!a || !b || running} className="w-full gap-2">
            <Play className={["h-4 w-4", running ? "animate-pulse" : ""].join(" ")} />
            {running ? "Running both variants…" : "Run paired comparison"}
          </Button>
        </CardContent>
      </Card>

      {eligible.length === 0 && (
        <Card>
          <CardContent className="p-12 text-center text-muted-foreground">
            <FlaskConical className="h-12 w-12 mx-auto mb-3 opacity-25" />
            <p className="font-medium text-foreground">No eval-bearing prompts</p>
            <p className="text-sm mt-1">A/B evidence needs a shared declared test set.</p>
          </CardContent>
        </Card>
      )}

      {result && <Comparison result={result} />}
    </div>
  );
}

function VariantPicker({
  label,
  prompts,
  prompt,
  model,
  setPrompt,
  setModel,
}: {
  label: string;
  prompts: PromptSummary[];
  prompt: string;
  model: string;
  setPrompt: (value: string) => void;
  setModel: (value: string) => void;
}) {
  return (
    <div className="rounded-xl border p-4 space-y-3">
      <p className="font-semibold">{label}</p>
      <select
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
      >
        {prompts.map((item) => (
          <option key={item.id} value={item.id}>{item.id}</option>
        ))}
      </select>
      <Input
        value={model}
        onChange={(event) => setModel(event.target.value)}
        placeholder="Optional model override: provider/model"
      />
    </div>
  );
}

function Comparison({ result }: { result: ExperimentResult }) {
  const comparison = result.comparison;
  const aScore = score(result.variant_a.report);
  const bScore = score(result.variant_b.report);
  const low = comparison.delta_ci.low;
  const high = comparison.delta_ci.high;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <VariantResult label="A" id={result.variant_a.prompt_id} model={result.variant_a.model} score={aScore} winner={comparison.winner === "a"} />
        <VariantResult label="B" id={result.variant_b.prompt_id} model={result.variant_b.model} score={bScore} winner={comparison.winner === "b"} />
      </div>
      <Card>
        <CardContent className="p-5 space-y-3">
          <div className="grid gap-3 sm:grid-cols-4 text-sm">
            <Datum label="Paired cases" value={String(comparison.paired_cases)} />
            <Datum label="Delta (B − A)" value={comparison.delta == null ? "withheld" : percent(comparison.delta)} />
            <Datum
              label="95% paired interval"
              value={low == null || high == null ? "withheld" : percent(low) + "–" + percent(high)}
            />
            <Datum label="Measured cost" value={comparison.cost_usd ? "$" + comparison.cost_usd.total.toFixed(6) : "—"} />
          </div>
          <div className={["rounded-lg border p-3 text-sm", comparison.winner ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-200" : "border-amber-500/25 bg-amber-500/5 text-amber-200"].join(" ")}>
            {comparison.reason}
          </div>
          {comparison.note && <p className="text-[11px] text-muted-foreground">{comparison.note}</p>}
        </CardContent>
      </Card>
    </div>
  );
}

function VariantResult({
  label,
  id,
  model,
  score,
  winner,
}: {
  label: string;
  id: string;
  model: string | null;
  score: number | null;
  winner: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-muted-foreground">Variant {label}</p>
            <p className="font-semibold mt-1">{id}</p>
            <p className="text-xs text-muted-foreground">{model || "prompt default model"}</p>
          </div>
          {winner && <Trophy className="h-5 w-5 text-emerald-400" />}
        </div>
        <p className="text-3xl font-bold mt-5">{score == null ? "withheld" : percent(score)}</p>
      </CardContent>
    </Card>
  );
}

function Datum({ label, value }: { label: string; value: string }) {
  return <div><p className="text-[10px] uppercase text-muted-foreground">{label}</p><p className="font-semibold mt-1">{value}</p></div>;
}

function score(report: ExperimentResult["variant_a"]["report"]): number | null {
  return typeof report.score === "number" && Number.isFinite(report.score) ? report.score : null;
}

function percent(value: number): string {
  return (value * 100).toFixed(1) + "%";
}

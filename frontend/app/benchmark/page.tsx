import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  CircleSlash2,
  Download,
  FlaskConical,
  Scale,
  ShieldAlert,
  Target,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
  BENCHMARK_SCORECARD,
  BenchmarkMetric,
} from "@/lib/benchmark-scorecard";

export default function BenchmarkPage() {
  const componentEvidence = BENCHMARK_SCORECARD.primary.filter(
    (metric) => metric.state === "component_verified",
  ).length;

  return (
    <div className="animate-fade-in space-y-6">
      <section className="overflow-hidden rounded-2xl border border-amber-500/25 bg-gradient-to-br from-amber-500/10 via-violet-500/5 to-transparent p-5 sm:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 shadow-lg shadow-amber-500/15">
              <Target className="h-6 w-6 text-white" aria-hidden="true" />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-400">
              Competitive proof gate
            </p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">
              Benchmark scorecard
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
              {BENCHMARK_SCORECARD.wedge}
            </p>
          </div>

          <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.07] p-4 lg:max-w-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-amber-400">
              <ShieldAlert className="h-4 w-4" aria-hidden="true" />
              {BENCHMARK_SCORECARD.claim}
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Internal component evidence is not a competitor result. The claim remains
              withheld until identical tasks are run fairly and independently reproduced.
            </p>
            <p className="mt-3 font-mono text-[10px] text-muted-foreground">
              {BENCHMARK_SCORECARD.snapshot}
            </p>
          </div>
        </div>

        <div className="mt-7 grid gap-3 sm:grid-cols-3" aria-label="Benchmark summary">
          <Summary value={String(BENCHMARK_SCORECARD.result.primary_kpi_count)} label="Primary KPIs" icon={Scale} />
          <Summary value={String(componentEvidence)} label="Component gates evidenced" icon={CheckCircle2} />
          <Summary value={String(BENCHMARK_SCORECARD.result.competitive_kpis_proven)} label="Competitive KPIs proven" icon={CircleSlash2} />
        </div>
      </section>

      <section aria-labelledby="primary-kpis-heading" className="space-y-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-violet-400">
            Published definitions
          </p>
          <h2 id="primary-kpis-heading" className="mt-1 text-xl font-semibold">
            Three primary KPIs
          </h2>
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          {BENCHMARK_SCORECARD.primary.map((metric) => (
            <MetricCard key={metric.id} metric={metric} />
          ))}
        </div>
      </section>

      <Card className="border-violet-500/25 bg-violet-500/[0.04]">
        <CardContent className="p-5 sm:p-6">
          <div className="flex gap-3">
            <FlaskConical className="mt-0.5 h-5 w-5 shrink-0 text-violet-400" aria-hidden="true" />
            <div>
              <h2 className="text-sm font-semibold">Rules that prevent a flattering benchmark</h2>
              <ul className="mt-3 space-y-2">
                {BENCHMARK_SCORECARD.guardrails.map((guardrail) => (
                  <li key={guardrail} className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                    {guardrail}
                  </li>
                ))}
              </ul>
              <a
                href={BENCHMARK_SCORECARD.operatorKit.file}
                download
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs font-semibold text-blue-300 hover:bg-blue-500/15"
              >
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                Download operator kit ({Math.ceil(BENCHMARK_SCORECARD.operatorKit.bytes / 1024)} KB)
              </a>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-blue-500/25 bg-blue-500/[0.04]">
        <CardContent className="p-5 sm:p-6">
          <div className="flex gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-blue-400" aria-hidden="true" />
            <div>
              <h2 className="text-sm font-semibold">Shared protocol kit ready</h2>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                The comparison inputs and evidence-capture path are now fixed. What remains is
                independent execution—not another change to the scoring rules.
              </p>
              <p className="mt-2 font-mono text-[10px] text-blue-300">
                {BENCHMARK_SCORECARD.plan.planned_trial_records} assignment slots planned across {BENCHMARK_SCORECARD.plan.product_ids.length} products · Role template—not evidence
              </p>
              <ul className="mt-3 space-y-2">
                {BENCHMARK_SCORECARD.protocolAssets.map((asset) => (
                  <li key={asset} className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
                    {asset}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-amber-500/25 bg-amber-500/[0.04]">
        <CardContent className="p-5 sm:p-6">
          <div className="flex gap-3">
            <CircleSlash2 className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" aria-hidden="true" />
            <div>
              <h2 className="text-sm font-semibold">Minimum evidence still required</h2>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {BENCHMARK_SCORECARD.result.qualifying_comparator_count} of {BENCHMARK_SCORECARD.result.minimum_comparators} required comparators currently qualify. The claim cannot move until every requirement below is satisfied.
              </p>
              <p className="mt-2 font-mono text-[10px] text-amber-300">
                {BENCHMARK_SCORECARD.result.recorded_trial_count} / {BENCHMARK_SCORECARD.result.minimum_qualifying_trial_records} minimum trial records captured · {BENCHMARK_SCORECARD.result.minimum_record_gap} record gap
              </p>
              <ul className="mt-3 space-y-2">
                {BENCHMARK_SCORECARD.minimumEvidence.map((requirement) => (
                  <li key={requirement} className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                    {requirement}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70">
        <CardContent className="p-5">
          <h2 className="text-sm font-semibold">Machine-verifiable evidence source</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            The claim state above is generated by the checked-in benchmark scorer, not typed
            into this page. Any trial or protocol change alters the recorded digest and must
            regenerate the portal projection.
          </p>
          <dl className="mt-3 grid gap-3 text-[10px] sm:grid-cols-3">
            <div className="rounded-lg border bg-background/60 p-3">
              <dt className="font-semibold text-foreground">Protocol SHA-256</dt>
              <dd className="mt-1 break-all font-mono text-muted-foreground">
                {BENCHMARK_SCORECARD.result.protocol_sha256}
              </dd>
            </div>
            <div className="rounded-lg border bg-background/60 p-3">
              <dt className="font-semibold text-foreground">Trial ledger SHA-256</dt>
              <dd className="mt-1 break-all font-mono text-muted-foreground">
                {BENCHMARK_SCORECARD.result.trials_sha256}
              </dd>
            </div>
            <div className="rounded-lg border bg-background/60 p-3">
              <dt className="font-semibold text-foreground">Operator kit SHA-256</dt>
              <dd className="mt-1 break-all font-mono text-muted-foreground">
                {BENCHMARK_SCORECARD.operatorKit.sha256}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Link
        href="/delivery"
        className="inline-flex items-center gap-1 text-xs font-semibold text-violet-400 hover:underline"
      >
        <ArrowLeft className="h-3 w-3" aria-hidden="true" /> Return to Delivery Status
      </Link>
    </div>
  );
}

function Summary({
  value,
  label,
  icon: Icon,
}: {
  value: string;
  label: string;
  icon: React.ElementType;
}) {
  return (
    <div className="rounded-xl border bg-background/55 p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        {label}
      </div>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}

function MetricCard({ metric }: { metric: BenchmarkMetric }) {
  const isMeasured = metric.state === "component_verified";
  return (
    <Card className={isMeasured ? "border-emerald-500/25" : "border-dashed"}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-sm font-semibold leading-snug">{metric.name}</h3>
          <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
            isMeasured
              ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-400"
              : "border-border bg-muted/30 text-muted-foreground"
          }`}>
            {isMeasured ? "Component evidence" : "Not measured"}
          </span>
        </div>

        <dl className="mt-4 space-y-3 text-[11px]">
          <Definition label="Unit" value={metric.unit} />
          <Definition label="Formula" value={metric.formula} />
          <Definition label="Release target" value={metric.releaseTarget} />
        </dl>

        <div className="mt-4 space-y-2 border-t pt-4">
          <Result label="Assay" value={metric.assayResult} positive={isMeasured} />
          <Result label="Best comparator" value={metric.comparatorResult} positive={false} />
        </div>

        <div className="mt-4 space-y-2">
          {metric.evidence.map((item) => (
            <p key={item} className="flex gap-2 text-[11px] leading-relaxed text-muted-foreground">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
              {item}
            </p>
          ))}
        </div>

        <div className="mt-4 rounded-lg border border-blue-500/25 bg-blue-500/[0.06] px-3 py-2 text-[11px] leading-relaxed text-blue-300">
          <span className="font-semibold">Next controlled run: </span>{metric.nextRun}
        </div>
      </CardContent>
    </Card>
  );
}

function Definition({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-semibold text-foreground">{label}</dt>
      <dd className="mt-0.5 leading-relaxed text-muted-foreground">{value}</dd>
    </div>
  );
}

function Result({ label, value, positive }: { label: string; value: string; positive: boolean }) {
  return (
    <div className="rounded-lg border bg-background/60 p-3">
      <p className="text-[9px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`mt-1 text-[11px] leading-relaxed ${positive ? "text-emerald-400" : "text-muted-foreground"}`}>
        {value}
      </p>
    </div>
  );
}

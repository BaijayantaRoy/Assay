import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  CircleDotDashed,
  Clock3,
  GitCommitHorizontal,
  Rocket,
  ShieldCheck,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
  DELIVERY_STATUS,
  DeliveryMilestone,
  DeliveryStage,
} from "@/lib/delivery-status";

const STAGE = {
  verified: {
    label: "Done · verified",
    shortLabel: "Verified",
    Icon: CheckCircle2,
    tone: "border-emerald-500/30 bg-emerald-500/5 text-emerald-400",
    card: "border-emerald-500/25",
  },
  in_progress: {
    label: "Being built",
    shortLabel: "In progress",
    Icon: CircleDotDashed,
    tone: "border-blue-500/35 bg-blue-500/10 text-blue-400",
    card: "border-blue-500/40 bg-blue-500/[0.03]",
  },
  queued: {
    label: "Next in sequence",
    shortLabel: "Next",
    Icon: Clock3,
    tone: "border-border bg-muted/30 text-muted-foreground",
    card: "border-dashed",
  },
} satisfies Record<DeliveryStage, {
  label: string;
  shortLabel: string;
  Icon: React.ElementType;
  tone: string;
  card: string;
}>;

const ORDER: DeliveryStage[] = ["verified", "in_progress", "queued"];

export default function DeliveryPage() {
  const counts = ORDER.reduce(
    (result, stage) => ({
      ...result,
      [stage]: DELIVERY_STATUS.milestones.filter((item) => item.stage === stage).length,
    }),
    {} as Record<DeliveryStage, number>,
  );

  return (
    <div className="animate-fade-in space-y-6">
      <section className="overflow-hidden rounded-2xl border border-blue-500/20 bg-gradient-to-br from-blue-500/10 via-violet-500/5 to-transparent p-5 sm:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-violet-500 shadow-lg shadow-blue-500/15">
              <Rocket className="h-6 w-6 text-white" aria-hidden="true" />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-400">
              Release transparency
            </p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">
              Delivery status
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
              {DELIVERY_STATUS.objective}
            </p>
          </div>

          <div className="rounded-xl border bg-background/60 p-4 text-xs backdrop-blur-sm lg:max-w-sm">
            <div className="flex items-center gap-2 font-semibold">
              <GitCommitHorizontal className="h-4 w-4 text-violet-400" aria-hidden="true" />
              Source-controlled snapshot
            </div>
            <p className="mt-2 leading-relaxed text-muted-foreground">
              This is not a simulated activity feed. Status changes with reviewed code and
              named evidence; no background task is implied.
            </p>
            <p className="mt-3 font-mono text-[10px] text-muted-foreground">
              {DELIVERY_STATUS.snapshot}
            </p>
          </div>
        </div>

        <div className="mt-7 grid grid-cols-3 gap-2 sm:gap-3" aria-label="Delivery summary">
          {ORDER.map((stage) => {
            const meta = STAGE[stage];
            return (
              <div key={stage} className="rounded-xl border bg-background/55 p-3 sm:p-4">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <meta.Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  <span className="text-[10px] uppercase tracking-wide sm:text-xs">
                    {meta.shortLabel}
                  </span>
                </div>
                <p className="mt-1 text-2xl font-bold">{counts[stage]}</p>
                <p className="hidden text-[10px] text-muted-foreground sm:block">
                  tracked milestone{counts[stage] === 1 ? "" : "s"}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-3">
        {ORDER.map((stage) => {
          const meta = STAGE[stage];
          const items = DELIVERY_STATUS.milestones
            .filter((item) => item.stage === stage)
            .sort((left, right) => {
              if (stage !== "verified") return 0;
              return Number(right.id === "release-matrix") - Number(left.id === "release-matrix");
            });
          return (
            <section key={stage} aria-labelledby={`${stage}-heading`} className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <meta.Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  <h2 id={`${stage}-heading`} className="text-sm font-semibold">
                    {meta.label}
                  </h2>
                </div>
                <span className="font-mono text-xs text-muted-foreground">{items.length}</span>
              </div>
              {items.map((item) => (
                <MilestoneCard key={item.id} item={item} />
              ))}
            </section>
          );
        })}
      </div>

      <Card className="border-violet-500/20 bg-violet-500/5">
        <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-violet-400" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold">The ledger follows Assay&apos;s own honesty rule</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                File presence is progress, not proof. An item becomes verified only when its
                stated scope has passed; broader release claims remain withheld.
              </p>
            </div>
          </div>
          <Link
            href="/benchmark"
            className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-violet-400 hover:underline"
          >
            Inspect the active benchmark <ArrowRight className="h-3 w-3" aria-hidden="true" />
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

function MilestoneCard({ item }: { item: DeliveryMilestone }) {
  const meta = STAGE[item.stage];
  return (
    <Card className={meta.card}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-sm font-semibold leading-snug">{item.title}</h3>
          <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${meta.tone}`}>
            {meta.shortLabel}
          </span>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{item.summary}</p>

        <div className="mt-4 space-y-3 border-t pt-4">
          {item.evidence.map((evidence) => (
            <div key={evidence.label} className="flex gap-2.5">
              <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                item.stage === "verified"
                  ? "bg-emerald-400"
                  : item.stage === "in_progress"
                    ? "bg-blue-400"
                    : "bg-muted-foreground/40"
              }`} />
              <div>
                {evidence.href ? (
                  <Link href={evidence.href} className="text-xs font-semibold hover:text-violet-400 hover:underline">
                    {evidence.label}
                  </Link>
                ) : (
                  <p className="text-xs font-semibold">{evidence.label}</p>
                )}
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                  {evidence.detail}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className={`mt-4 rounded-lg border px-3 py-2 text-[11px] leading-relaxed ${meta.tone}`}>
          {item.verification}
        </div>
      </CardContent>
    </Card>
  );
}

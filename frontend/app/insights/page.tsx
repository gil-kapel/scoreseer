import { Lightbulb } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { api, safe, type InsightItem } from "@/lib/api";
import { estimatorFromModelId } from "@/lib/estimators";
import { fmtKickoff } from "@/lib/format";

export const revalidate = 45;

function Note({ it }: { it: InsightItem }) {
  const est = estimatorFromModelId(it.model_id);
  return (
    <Link href={`/matches/${it.fixture_id}`} className="block">
      <Card className="border-l-2 border-l-primary p-4 transition-colors hover:border-primary/50">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-fg">
            {it.home} <span className="text-fg-muted">v</span> {it.away}
          </span>
          <span className="nums shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-xs font-medium text-primary">
            {it.predicted}
          </span>
        </div>
        <p className="line-clamp-4 text-sm leading-relaxed text-fg-muted">{it.explanation}</p>
        <div className="label mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-fg-muted">
            {est.icon} {est.name}
          </span>
          <span className="text-border">·</span>
          <span className="text-primary">{Math.round(it.confidence * 100)}% conf</span>
          <span className="text-border">·</span>
          <span>
            {it.played ? "played" : "upcoming"} · {fmtKickoff(it.kickoff_utc)}
          </span>
        </div>
      </Card>
    </Link>
  );
}

export default async function InsightsPage() {
  const { data, error } = await safe(api.insights(40));
  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-fg">
          <Lightbulb className="h-5 w-5 text-primary" /> Insights
        </h1>
        <p className="text-sm text-fg-muted">
          LLM analyst notes — the reasoning behind each prediction, newest first.
        </p>
      </header>

      {error ? (
        <Card className="p-6 text-sm text-danger">Couldn&apos;t load insights: {error}</Card>
      ) : !data || data.length === 0 ? (
        <Card className="p-6 text-sm text-fg-muted">
          No LLM notes yet — run a prediction (Admin → batch) and they&apos;ll appear here.
        </Card>
      ) : (
        <div className="space-y-3">
          {data.map((it) => (
            <Note key={it.fixture_id} it={it} />
          ))}
        </div>
      )}
    </div>
  );
}

import { ExternalLink, Loader2 } from "lucide-react";
import Link from "next/link";

import { GradeBadges } from "@/components/grade-badges";
import { PredictMatchButton } from "@/components/predict-match-button";
import { ConfidenceMeter, ScoreLine, ScorersByTeam } from "@/components/prediction-ui";
import { AutoRefresh } from "@/components/run-controls";
import { StatusChip } from "@/components/status-chip";
import { TeamFlag } from "@/components/team-flag";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { api, safe, type MatchDetail } from "@/lib/api";
import { fmtKickoff, pct } from "@/lib/format";

export const dynamic = "force-dynamic";

function MatchHeader({ m }: { m: MatchDetail }) {
  const { fixture } = m;
  return (
    <div className="flex items-center justify-between">
      <div>
        <div className="text-xs text-fg-muted">
          {fixture.stage}
          {fixture.group_label ? ` · ${fixture.group_label}` : ""} · {fmtKickoff(fixture.kickoff_utc)}
        </div>
        <div className="mt-2 flex items-center gap-3 text-lg font-semibold text-fg">
          <TeamFlag team={fixture.home} size={24} />
          {fixture.home.name}
          <span className="px-1 text-sm text-fg-muted">v</span>
          {fixture.away.name}
          <TeamFlag team={fixture.away} size={24} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <StatusChip status={fixture.prediction_status} />
        <PredictMatchButton fixtureId={fixture.id} predicting={m.predicting} />
      </div>
    </div>
  );
}

function PredictionPanel({ m }: { m: MatchDetail }) {
  const p = m.prediction;
  return (
    <Card className="space-y-4 p-5">
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-fg-muted">Prediction</div>
        {p?.is_backfill ? (
          <Badge tone="warning" title="Predicted after the match — excluded from accuracy & calibration">
            Backfill · excluded
          </Badge>
        ) : null}
      </div>
      {!p ? (
        <p className="text-sm text-fg-muted">Not predicted yet.</p>
      ) : p.status !== "ok" ? (
        <p className="text-sm text-danger">Prediction failed: {p.failure_reason}</p>
      ) : (
        <>
          <div className="flex items-center gap-4">
            <ScoreLine home={p.home_score} away={p.away_score} size="lg" />
            <ConfidenceMeter value={p.match_confidence} />
          </div>
          <div>
            <div className="mb-2 text-xs uppercase tracking-wide text-fg-muted">
              Likely scorers
            </div>
            {p.scorers.length === 0 ? (
              <p className="text-xs text-fg-muted">
                This estimator predicts the scoreline only — no individual scorers.
              </p>
            ) : (
              <ScorersByTeam scorers={p.scorers} home={m.fixture.home} away={m.fixture.away} />
            )}
          </div>
          <p className="border-t border-border pt-3 text-sm leading-relaxed text-fg-muted">
            {p.explanation}
          </p>
          <div className="text-[10px] text-fg-muted">
            {p.model_id} · {p.prompt_version} · calibration v{p.calibration_version}
          </div>
        </>
      )}
    </Card>
  );
}

function ResultPanel({ m }: { m: MatchDetail }) {
  const r = m.result;
  return (
    <Card className="space-y-4 p-5">
      <div className="text-xs uppercase tracking-wide text-fg-muted">Actual result</div>
      {!r ? (
        <p className="text-sm text-fg-muted">Awaiting result — kickoff {fmtKickoff(m.fixture.kickoff_utc)}.</p>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <ScoreLine home={r.home_score_90} away={r.away_score_90} size="lg" />
            <Badge tone="neutral">90&apos; · {r.decided_by}</Badge>
          </div>
          {r.scorers.length > 0 ? (
            <ul className="space-y-1 text-sm text-fg">
              {r.scorers.map((s, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="nums w-8 text-fg-muted">{s.minute ? `${s.minute}'` : ""}</span>
                  {s.player_name}
                  {s.type !== "goal" ? (
                    <span className="text-xs text-fg-muted">({s.type})</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-fg-muted">No goalscorer data from the source.</p>
          )}
        </>
      )}
    </Card>
  );
}

export default async function MatchDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { data: m, error } = await safe(api.matchDetail(id));

  if (error || !m) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-primary">
          ← Back
        </Link>
        <Card className="p-6 text-sm text-danger">Couldn&apos;t load match: {error}</Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-fg-muted hover:text-fg">
        ← Upcoming
      </Link>
      <MatchHeader m={m} />

      {m.predicting ? (
        <Card className="flex items-center gap-3 border-primary/40 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />
          <div>
            <div className="text-sm font-medium text-fg">Predicting this match…</div>
            <div className="text-xs text-fg-muted">
              Running web search + LLM — usually a few minutes. This page refreshes itself; your
              current estimate below stays until the new one is ready.
            </div>
          </div>
          <AutoRefresh active />
        </Card>
      ) : null}

      {m.grade ? (
        <Card className="space-y-2 p-4">
          <div className="text-xs uppercase tracking-wide text-fg-muted">Grade</div>
          <GradeBadges grade={m.grade} />
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <PredictionPanel m={m} />
        <ResultPanel m={m} />
      </div>

      {m.estimators.length > 1 ? (
        <Card className="space-y-3 p-5">
          <div className="text-xs uppercase tracking-wide text-fg-muted">Estimators</div>
          <div className="grid gap-3 sm:grid-cols-2">
            {m.estimators.map((e) => (
              <div key={e.id} className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-fg">
                    {e.model_id === "poisson-v1" ? "📊 Poisson" : "🤖 LLM"}
                  </span>
                  <ScoreLine home={e.home_score} away={e.away_score} />
                </div>
                <div className="mt-1 nums text-[10px] text-fg-muted">
                  {Math.round(e.match_confidence * 100)}% confidence
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <Card className="space-y-3 p-5">
        <div className="flex items-center justify-between">
          <div className="text-xs uppercase tracking-wide text-fg-muted">Evidence</div>
          {m.data_quality ? (
            <Badge tone={m.data_quality === "ok" ? "neutral" : "warning"}>
              data: {m.data_quality}
            </Badge>
          ) : null}
        </div>
        {m.sources.length === 0 ? (
          <p className="text-sm text-fg-muted">No sources recorded for this prediction.</p>
        ) : (
          <ul className="grid gap-1 md:grid-cols-2">
            {m.sources.slice(0, 12).map((s, i) => (
              <li key={i}>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 truncate text-xs text-info hover:underline"
                >
                  <ExternalLink className="h-3 w-3 shrink-0" />
                  <span className="truncate">{s.title ?? s.url}</span>
                </a>
              </li>
            ))}
          </ul>
        )}
        {m.sources.length > 12 ? (
          <div className="text-xs text-fg-muted">+ {m.sources.length - 12} more sources</div>
        ) : null}
      </Card>
    </div>
  );
}

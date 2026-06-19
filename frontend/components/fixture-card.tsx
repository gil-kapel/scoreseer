import Link from "next/link";

import { ConfidenceMeter, ScoreLine } from "@/components/prediction-ui";
import { StatusChip } from "@/components/status-chip";
import { TeamFlag } from "@/components/team-flag";
import { Card } from "@/components/ui/card";
import type { FixtureRead } from "@/lib/api";
import { fmtKickoff } from "@/lib/format";

export function FixtureCard({ fixture }: { fixture: FixtureRead }) {
  const p = fixture.prediction;
  return (
    <Link href={`/matches/${fixture.id}`} className="block">
      <Card className="px-4 py-3 transition-colors hover:border-primary/40">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <div className="w-24 shrink-0 text-xs text-fg-muted">
              {fixture.group_label ?? fixture.stage}
            </div>
            <div className="flex items-center gap-2">
              <TeamFlag team={fixture.home} />
              <span className="nums font-medium text-fg">{fixture.home.code}</span>
              <span className="px-1 text-xs text-fg-muted">v</span>
              <span className="nums font-medium text-fg">{fixture.away.code}</span>
              <TeamFlag team={fixture.away} />
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-5">
            {p ? (
              <div className="flex items-center gap-3">
                <span className="text-[10px] uppercase tracking-wide text-fg-muted">pred</span>
                <ScoreLine home={p.home_score} away={p.away_score} />
                <ConfidenceMeter value={p.match_confidence} />
              </div>
            ) : (
              <span className="text-xs text-fg-muted">not predicted</span>
            )}
            <span className="nums w-28 text-right text-xs text-fg-muted">
              {fmtKickoff(fixture.kickoff_utc)}
            </span>
            <StatusChip status={fixture.prediction_status} />
          </div>
        </div>
      </Card>
    </Link>
  );
}

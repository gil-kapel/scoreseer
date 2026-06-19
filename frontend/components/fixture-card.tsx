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
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          {/* Row 1 on mobile: teams + status. Desktop: group label + teams. */}
          <div className="flex items-center justify-between gap-3 sm:min-w-0 sm:justify-start sm:gap-4">
            <div className="hidden w-24 shrink-0 text-xs text-fg-muted sm:block">
              {fixture.group_label ?? fixture.stage}
            </div>
            <div className="flex items-center gap-2">
              <TeamFlag team={fixture.home} />
              <span className="nums font-medium text-fg">{fixture.home.code}</span>
              <span className="px-1 text-xs text-fg-muted">v</span>
              <span className="nums font-medium text-fg">{fixture.away.code}</span>
              <TeamFlag team={fixture.away} />
            </div>
            <div className="sm:hidden">
              <StatusChip status={fixture.prediction_status} />
            </div>
          </div>

          {/* Row 2 on mobile: group·time + prediction. Desktop: pred + time + status. */}
          <div className="flex items-center justify-between gap-3 sm:shrink-0 sm:justify-end sm:gap-5">
            <span className="nums text-xs text-fg-muted sm:hidden">
              {(fixture.group_label ?? fixture.stage)} · {fmtKickoff(fixture.kickoff_utc)}
            </span>
            {p ? (
              <div className="flex items-center gap-3">
                <span className="hidden text-[10px] uppercase tracking-wide text-fg-muted sm:inline">
                  pred
                </span>
                <ScoreLine home={p.home_score} away={p.away_score} />
                <ConfidenceMeter value={p.match_confidence} />
              </div>
            ) : (
              <span className="text-xs text-fg-muted">not predicted</span>
            )}
            <span className="nums hidden w-28 text-right text-xs text-fg-muted sm:inline">
              {fmtKickoff(fixture.kickoff_utc)}
            </span>
            <div className="hidden sm:block">
              <StatusChip status={fixture.prediction_status} />
            </div>
          </div>
        </div>
      </Card>
    </Link>
  );
}

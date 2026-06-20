"use client";

import Link from "next/link";
import { useState } from "react";

import { TeamFlag } from "@/components/team-flag";
import { Card } from "@/components/ui/card";
import { WinProbBar } from "@/components/win-prob-bar";
import type { FixtureRead } from "@/lib/api";
import { fmtKickoff } from "@/lib/format";
import { deriveSplit } from "@/lib/winprob";

export function ForecastBoard({ fixtures }: { fixtures: FixtureRead[] }) {
  const [minConf, setMinConf] = useState(0);
  const rows = fixtures
    .filter((f) => f.prediction && f.prediction.match_confidence >= minConf)
    .sort((a, b) => b.prediction!.match_confidence - a.prediction!.match_confidence);

  return (
    <div className="space-y-5">
      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="label">confidence filter</span>
          <span className="nums text-sm font-medium text-primary">{Math.round(minConf * 100)}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={90}
          value={Math.round(minConf * 100)}
          onChange={(e) => setMinConf(Number(e.target.value) / 100)}
          className="w-full"
          style={{ accentColor: "var(--color-primary)" }}
        />
        <div className="label mt-1 flex justify-between">
          <span>all calls</span>
          <span>only confident</span>
        </div>
      </Card>

      {rows.length === 0 ? (
        <Card className="p-6 text-sm text-fg-muted">No predictions above this confidence.</Card>
      ) : (
        <div className="space-y-2">
          {rows.map((f) => {
            const p = f.prediction!;
            return (
              <Link key={f.id} href={`/matches/${f.id}`} className="block">
                <Card className="p-4 transition-colors hover:border-primary/40">
                  <div className="mb-2.5 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <TeamFlag team={f.home} />
                      <span className="nums font-medium text-fg">{f.home.code}</span>
                      <span className="px-0.5 text-xs text-fg-muted">v</span>
                      <span className="nums font-medium text-fg">{f.away.code}</span>
                      <TeamFlag team={f.away} />
                    </div>
                    <span className="nums shrink-0 text-xs text-fg-muted">
                      {fmtKickoff(f.kickoff_utc)}
                    </span>
                  </div>
                  <WinProbBar
                    split={deriveSplit(p.home_score, p.away_score, p.match_confidence)}
                    home={f.home.code}
                    away={f.away.code}
                  />
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

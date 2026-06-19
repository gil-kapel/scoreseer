import { TeamFlag } from "@/components/team-flag";
import { cn } from "@/lib/cn";
import type { ScorerPred, TeamBrief } from "@/lib/api";

export function ScoreLine({
  home,
  away,
  size = "md",
}: {
  home: number;
  away: number;
  size?: "md" | "lg";
}) {
  return (
    <span className={cn("nums font-semibold text-fg", size === "lg" && "text-4xl")}>
      {home}
      <span className="px-1 text-fg-muted">–</span>
      {away}
    </span>
  );
}

export function ConfidenceMeter({ value }: { value: number }) {
  const pctv = Math.round(value * 100);
  const tone = value >= 0.66 ? "bg-success" : value >= 0.4 ? "bg-warning" : "bg-danger";
  return (
    <span className="inline-flex items-center gap-2" title="match confidence">
      <span className="block h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
        <span className={cn("block h-full rounded-full", tone)} style={{ width: `${pctv}%` }} />
      </span>
      <span className="nums text-xs text-fg-muted">{pctv}%</span>
    </span>
  );
}

function ScorerRow({ s }: { s: ScorerPred }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <span className="flex-1 truncate text-fg">{s.player_name}</span>
      <span className="block h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
        <span
          className="block h-full rounded-full bg-primary"
          style={{ width: `${Math.round(s.likelihood * 100)}%` }}
        />
      </span>
      <span className="nums w-9 text-right text-xs text-fg-muted">
        {Math.round(s.likelihood * 100)}%
      </span>
    </li>
  );
}

function TeamScorers({ team, scorers }: { team: TeamBrief; scorers: ScorerPred[] }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 border-b border-border pb-1.5 text-xs font-medium text-fg-muted">
        <TeamFlag team={team} size={16} />
        <span className="nums">{team.code}</span>
        <span className="truncate font-normal">{team.name}</span>
      </div>
      {scorers.length === 0 ? (
        <p className="text-xs text-fg-muted">None predicted</p>
      ) : (
        <ul className="space-y-1.5">
          {scorers.map((s, i) => (
            <ScorerRow key={i} s={s} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function ScorersByTeam({
  scorers,
  home,
  away,
}: {
  scorers: ScorerPred[];
  home: TeamBrief;
  away: TeamBrief;
}) {
  return (
    <div className="grid grid-cols-2 gap-5">
      <TeamScorers team={home} scorers={scorers.filter((s) => s.team === "home")} />
      <TeamScorers team={away} scorers={scorers.filter((s) => s.team === "away")} />
    </div>
  );
}

import { cn } from "@/lib/cn";
import type { TeamBrief } from "@/lib/api";

export function TeamFlag({ team, size = 20 }: { team: TeamBrief; size?: number }) {
  if (team.crest_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={team.crest_url}
        alt={team.name}
        width={size}
        height={size}
        className="inline-block rounded-sm object-contain"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      className="inline-flex items-center justify-center rounded-sm bg-surface-2 text-[9px] text-fg-muted"
      style={{ width: size, height: size }}
    >
      {team.code.slice(0, 3)}
    </span>
  );
}

export function TeamLabel({ team, className }: { team: TeamBrief; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <TeamFlag team={team} />
      <span className="nums font-medium text-fg">{team.code}</span>
    </span>
  );
}

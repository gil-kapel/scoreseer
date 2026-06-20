import type { Split } from "@/lib/winprob";

/** Win-probability split bar — green (home) · gray (draw) · blue (away), the mockup
 *  signature. `compact` hides the labels (for dense lists / cards). */
export function WinProbBar({
  split,
  home,
  away,
  compact = false,
}: {
  split: Split;
  home: string;
  away: string;
  compact?: boolean;
}) {
  const segs = [
    { pct: split.home, cls: "bg-primary" },
    { pct: split.draw, cls: "bg-neutral/70" },
    { pct: split.away, cls: "bg-info" },
  ];
  return (
    <div className="w-full">
      {!compact ? (
        <div className="mb-1 flex items-center justify-between">
          <span className="label text-primary">win probability</span>
          <span className="label text-info">fair value split</span>
        </div>
      ) : null}
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-surface-2">
        {segs.map((s, i) => (
          <div key={i} className={s.cls} style={{ width: `${Math.max(0, s.pct) * 100}%` }} />
        ))}
      </div>
      {!compact ? (
        <div className="mt-1.5 flex items-center justify-between nums text-xs">
          <span className="font-medium text-primary">
            {Math.round(split.home * 100)}% {home}
          </span>
          <span className="text-fg-muted">{Math.round(split.draw * 100)}% Draw</span>
          <span className="font-medium text-info">
            {Math.round(split.away * 100)}% {away}
          </span>
        </div>
      ) : null}
    </div>
  );
}

import type { StagePoints } from "@/lib/api";

const STAGE_LABELS: Record<string, string> = {
  group: "Group stage",
  r32: "Round of 32",
  r16: "Round of 16",
  qf: "Quarter-final",
  sf: "Semi-final",
  third_place: "3rd place",
  final: "Final",
};

export function StagePointsBreakdown({ stages }: { stages: StagePoints[] }) {
  if (stages.length === 0) {
    return <p className="text-sm text-muted-foreground">No graded matches yet.</p>;
  }
  return (
    <div className="space-y-2.5">
      {stages.map((s) => {
        const ratio = s.max_points ? s.points / s.max_points : 0;
        return (
          <div key={s.stage} className="flex items-center gap-3">
            <span className="w-28 shrink-0 text-xs text-muted-foreground">
              {STAGE_LABELS[s.stage] ?? s.stage}
            </span>
            <span className="block h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
              <span
                className="block h-full rounded-full bg-primary"
                style={{ width: `${Math.round(ratio * 100)}%` }}
              />
            </span>
            <span className="nums w-16 text-right text-xs font-medium text-foreground">
              {s.points}/{s.max_points}
            </span>
            <span className="nums w-12 text-right text-[10px] text-muted-foreground">
              {s.n} {s.n === 1 ? "match" : "matches"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

import { BarChart3 } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import type { DashboardMetrics } from "@/lib/api";
import { fixed, pct } from "@/lib/format";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex shrink-0 items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</span>
      <span className="nums text-sm font-medium text-fg">{value}</span>
    </div>
  );
}

export function HeaderStrip({ metrics }: { metrics: DashboardMetrics | null }) {
  const m = metrics && metrics.n_graded > 0 ? metrics : null;
  return (
    <div className="flex items-center gap-3 border-b border-border bg-surface px-4 py-2 md:gap-6 md:px-6 md:py-2.5">
      {/* Brand on mobile (the sidebar that normally shows it is hidden); label on desktop. */}
      <span className="flex shrink-0 items-center gap-1.5 text-sm font-semibold tracking-wide text-primary text-glow md:hidden">
        <BarChart3 className="h-4 w-4" />
        ScoreSeer
      </span>
      {/* Stats scroll horizontally on a narrow phone instead of wrapping/overflowing. */}
      <div className="flex flex-1 items-center gap-4 overflow-x-auto md:gap-6">
        <span className="hidden shrink-0 text-xs font-semibold text-fg-muted md:inline">
          Tournament
        </span>
        <div className="flex shrink-0 items-baseline gap-1.5 whitespace-nowrap">
          <span className="text-[10px] uppercase tracking-wide text-primary">Score</span>
          <span className="nums text-sm font-semibold text-primary">
            {m ? `${m.total_points}` : "—"}
          </span>
          {m ? <span className="nums text-[10px] text-fg-muted">/ {m.max_points}</span> : null}
        </div>
        <Stat label="Graded" value={m ? String(m.n_graded) : "—"} />
        <Stat label="Outcome" value={m ? pct(m.outcome_accuracy) : "—"} />
        <Stat label="Exact" value={m ? pct(m.exact_rate) : "—"} />
        <Stat label="Goals MAE" value={m ? fixed(m.goals_mae) : "—"} />
        <Stat label="Conf. Brier" value={m ? fixed(m.confidence_brier, 3) : "—"} />
      </div>
      <div className="shrink-0">
        <ThemeToggle />
      </div>
    </div>
  );
}

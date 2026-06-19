import { Check, Minus, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { GradeRead } from "@/lib/api";

function Verdict({ label, hit }: { label: string; hit: boolean | null }) {
  if (hit === null) return <Badge tone="neutral"><Minus className="h-3 w-3" />{label}</Badge>;
  return (
    <Badge tone={hit ? "success" : "danger"}>
      {hit ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
      {label}
    </Badge>
  );
}

export function GradeBadges({ grade }: { grade: GradeRead }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge tone={grade.points > 0 ? "primary" : "neutral"}>
        {grade.points} {grade.points === 1 ? "point" : "points"}
      </Badge>
      <Verdict label="Exact score" hit={grade.exact_hit} />
      <Verdict label="Outcome" hit={grade.outcome_correct} />
      <Badge tone="neutral">Goals err {grade.goals_abs_error}</Badge>
      <Badge tone="neutral">Scorer recall {Math.round(grade.scorer_recall * 100)}%</Badge>
      <Badge tone="neutral">Conf. Brier {grade.confidence_brier.toFixed(3)}</Badge>
      {grade.advancing_correct !== null ? (
        <Verdict label="Advanced" hit={grade.advancing_correct} />
      ) : null}
    </div>
  );
}

import { FlaskConical } from "lucide-react";

import { EstimatorRadar } from "@/components/charts/estimator-radar";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, safe, type EstimatorStats } from "@/lib/api";
import { estimatorIcon } from "@/lib/estimators";
import { fixed, pct } from "@/lib/format";

export const revalidate = 45;

type Metric = {
  label: string;
  hint: string;
  fmt: (e: EstimatorStats) => string;
  score: (e: EstimatorStats) => number; // higher = better (for highlighting)
};

const METRICS: Metric[] = [
  { label: "Outcome correct", hint: "1 / X / 2", fmt: (e) => pct(e.outcome_accuracy), score: (e) => e.outcome_accuracy },
  { label: "Exact score", hint: "90-min line", fmt: (e) => pct(e.exact_rate), score: (e) => e.exact_rate },
  { label: "Points", hint: "stage-weighted", fmt: (e) => `${e.total_points} / ${e.max_points}`, score: (e) => e.total_points },
  { label: "Goals MAE", hint: "lower is better", fmt: (e) => fixed(e.goals_mae), score: (e) => -e.goals_mae },
  { label: "Conf. Brier", hint: "lower is better", fmt: (e) => fixed(e.confidence_brier, 3), score: (e) => -e.confidence_brier },
];

const ICON = estimatorIcon;

export default async function EstimatorsPage() {
  const { data, error } = await safe(api.estimators());
  const estimators = data ?? [];
  const ranked = [...estimators].sort((a, b) => b.total_points - a.total_points);
  const leader = ranked[0];
  const runnerUp = ranked[1];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-fg">
          <FlaskConical className="h-5 w-5 text-primary" /> Lab
        </h1>
        <p className="max-w-xl text-sm text-fg-muted">
          Every estimator graded on the same matches, hindsight-free. 📊 Poisson, 📈 Elo, 📐
          Dixon-Coles and a 🪙 Naive floor are free baselines; 💱 Market is bookmaker odds; 🤖 LLM
          is Claude. Highest value per row is highlighted.
        </p>
      </header>

      {error ? (
        <Card className="p-6 text-sm text-danger">Couldn&apos;t load estimators: {error}</Card>
      ) : estimators.length === 0 ? (
        <Card className="p-6 text-sm text-fg-muted">
          No graded predictions yet — run predictions + grade, then compare here.
        </Card>
      ) : (
        <>
          {leader && runnerUp ? (
            <Card className="p-5">
              <div className="text-sm text-fg">
                <span className="font-semibold text-primary">
                  {ICON(leader.estimator)} {leader.estimator} leads
                </span>{" "}
                — {pct(leader.outcome_accuracy)} outcomes &amp; {leader.total_points} pts vs{" "}
                {runnerUp.estimator}&apos;s {pct(runnerUp.outcome_accuracy)} &amp;{" "}
                {runnerUp.total_points} pts, over {leader.n_graded} graded matches.
              </div>
            </Card>
          ) : null}

          {estimators.length >= 2 ? (
            <Card className="p-5">
              <div className="label mb-3">performance vectors · relative</div>
              <EstimatorRadar estimators={ranked.slice(0, 4)} />
            </Card>
          ) : null}

          <Card className="overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Metric</TableHead>
                  {estimators.map((e) => (
                    <TableHead key={e.estimator} className="text-right">
                      {ICON(e.estimator)} {e.estimator}
                      <span className="ml-1 text-[10px] font-normal text-fg-muted">
                        ({e.n_graded})
                      </span>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {METRICS.map((m) => {
                  const best = Math.max(...estimators.map((e) => m.score(e)));
                  return (
                    <TableRow key={m.label}>
                      <TableCell className="text-sm text-fg">
                        {m.label}
                        <span className="ml-2 text-[10px] text-fg-muted">{m.hint}</span>
                      </TableCell>
                      {estimators.map((e) => {
                        const isBest = m.score(e) === best && estimators.length > 1;
                        return (
                          <TableCell
                            key={e.estimator}
                            className={
                              "nums text-right text-sm " +
                              (isBest ? "font-semibold text-success" : "text-fg-muted")
                            }
                          >
                            {m.fmt(e)}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Card>
        </>
      )}
    </div>
  );
}

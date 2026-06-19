import { ReliabilityChart } from "@/components/charts/reliability-chart";
import { TrendChart } from "@/components/charts/trend-chart";
import { MetricTile } from "@/components/metric-tile";
import { StagePointsBreakdown } from "@/components/stage-points";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, safe } from "@/lib/api";
import { fixed, pct } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [{ data: metrics, error }, { data: cal }] = await Promise.all([
    safe(api.metrics()),
    safe(api.calibration()),
  ]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-fg">Accuracy dashboard</h1>
        <p className="text-sm text-fg-muted">
          Genuine forward predictions only.
          {metrics && metrics.backfill_excluded > 0
            ? ` ${metrics.backfill_excluded} backfill (hindsight) match${
                metrics.backfill_excluded === 1 ? "" : "es"
              } excluded from these stats & calibration.`
            : ""}
        </p>
      </header>

      {error ? (
        <Card className="p-6 text-sm text-danger">Couldn&apos;t compute metrics: {error}</Card>
      ) : !metrics || metrics.n_graded === 0 ? (
        <Card className="p-6 text-sm text-fg-muted">
          No graded matches yet — metrics appear once results come in.
        </Card>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <MetricTile
              label="Estimator score"
              value={String(metrics.total_points)}
              hint={`of ${metrics.max_points} possible`}
            />
            <MetricTile label="Graded" value={String(metrics.n_graded)} hint="matches" />
            <MetricTile label="Outcome" value={pct(metrics.outcome_accuracy)} hint="1/X/2 correct" />
            <MetricTile label="Exact score" value={pct(metrics.exact_rate)} hint="90-min line" />
            <MetricTile label="Goals MAE" value={fixed(metrics.goals_mae)} hint="total goals" />
            <MetricTile
              label="Conf. Brier"
              value={fixed(metrics.confidence_brier, 3)}
              hint="lower better"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Score & accuracy over matchdays</CardTitle>
              </CardHeader>
              <CardContent className="pt-2">
                <TrendChart points={metrics.trend} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Points by stage</CardTitle>
              </CardHeader>
              <CardContent className="pt-2">
                <StagePointsBreakdown stages={metrics.points_by_stage} />
              </CardContent>
            </Card>
          </div>

          {cal && cal.current ? (
            <Card className="space-y-4 p-4">
              <div className="flex items-center justify-between">
                <div className="text-xs uppercase tracking-wide text-fg-muted">
                  Calibration · v{cal.current.version}
                </div>
                {cal.first_half_brier !== null && cal.second_half_brier !== null ? (
                  <Badge tone={cal.second_half_brier <= cal.first_half_brier ? "success" : "warning"}>
                    Brier {fixed(cal.first_half_brier, 3)} → {fixed(cal.second_half_brier, 3)}
                    {cal.second_half_brier <= cal.first_half_brier ? " ↓ improving" : " ↑"}
                  </Badge>
                ) : null}
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <div className="mb-2 text-[10px] uppercase tracking-wide text-fg-muted">
                    Reliability — predicted confidence vs actual accuracy
                  </div>
                  <ReliabilityChart bins={cal.reliability} />
                </div>
                <div className="space-y-3">
                  <div>
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-fg-muted">
                      Observed bias
                    </div>
                    <p className="text-sm text-fg">{cal.current.bias_summary}</p>
                  </div>
                  {cal.prompt_snippet ? (
                    <div>
                      <div className="mb-1 text-[10px] uppercase tracking-wide text-fg-muted">
                        Injected into future predictions
                      </div>
                      <p className="rounded-md bg-surface-2 p-3 text-xs leading-relaxed text-fg-muted">
                        {cal.prompt_snippet}
                      </p>
                    </div>
                  ) : null}
                </div>
              </div>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  );
}

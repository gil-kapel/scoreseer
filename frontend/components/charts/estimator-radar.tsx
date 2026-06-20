"use client";

import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { EstimatorStats } from "@/lib/api";

type Axis = { key: string; get: (e: EstimatorStats) => number; higher: boolean };

const AXES: Axis[] = [
  { key: "Outcome", get: (e) => e.outcome_accuracy, higher: true },
  { key: "Exact", get: (e) => e.exact_rate, higher: true },
  { key: "Points", get: (e) => (e.max_points ? e.total_points / e.max_points : 0), higher: true },
  { key: "Goals", get: (e) => e.goals_mae, higher: false },
  { key: "Calibration", get: (e) => e.confidence_brier, higher: false },
];

const COLORS = [
  "var(--color-primary)",
  "var(--color-info)",
  "var(--color-warning)",
  "var(--color-neutral)",
  "var(--color-danger)",
];

/** Performance vectors — each axis min-max normalized across estimators so higher is
 *  always better (Goals/Calibration are inverted). Relative, not absolute. */
export function EstimatorRadar({ estimators }: { estimators: EstimatorStats[] }) {
  const scales = AXES.map((ax) => {
    const vals = estimators.map(ax.get);
    const min = Math.min(...vals);
    const span = Math.max(...vals) - min || 1;
    return (v: number) => {
      const t = (v - min) / span;
      return Math.round((0.15 + 0.85 * (ax.higher ? t : 1 - t)) * 100);
    };
  });
  const data = AXES.map((ax, i) => {
    const row: Record<string, number | string> = { axis: ax.key };
    estimators.forEach((e) => {
      row[e.estimator] = scales[i](ax.get(e));
    });
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data} outerRadius="70%">
        <PolarGrid stroke="var(--color-border)" />
        <PolarAngleAxis dataKey="axis" tick={{ fill: "var(--color-fg-muted)", fontSize: 11 }} />
        {estimators.map((e, i) => (
          <Radar
            key={e.estimator}
            name={e.estimator}
            dataKey={e.estimator}
            stroke={COLORS[i % COLORS.length]}
            fill={COLORS[i % COLORS.length]}
            fillOpacity={0.1}
            strokeWidth={2}
          />
        ))}
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            background: "var(--color-surface-2)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}

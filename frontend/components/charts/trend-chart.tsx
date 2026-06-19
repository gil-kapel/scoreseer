"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TrendPoint } from "@/lib/api";

export function TrendChart({ points }: { points: TrendPoint[] }) {
  const data = points.map((p) => ({
    date: p.date.slice(5),
    Outcome: Math.round(p.cumulative_outcome * 100),
    Exact: Math.round(p.cumulative_exact * 100),
    Score: p.cumulative_points,
  }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -20 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis dataKey="date" tick={{ fill: "var(--color-fg-muted)", fontSize: 11 }} />
        <YAxis
          yAxisId="pct"
          domain={[0, 100]}
          tick={{ fill: "var(--color-fg-muted)", fontSize: 11 }}
          unit="%"
        />
        <YAxis
          yAxisId="pts"
          orientation="right"
          tick={{ fill: "var(--color-fg-muted)", fontSize: 11 }}
          width={32}
        />
        <Tooltip
          contentStyle={{
            background: "var(--color-surface-2)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "var(--color-fg)" }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line yAxisId="pct" type="monotone" dataKey="Outcome" stroke="var(--color-primary)" strokeWidth={2} dot={false} />
        <Line yAxisId="pct" type="monotone" dataKey="Exact" stroke="var(--color-info)" strokeWidth={2} dot={false} />
        <Line yAxisId="pts" type="monotone" dataKey="Score" stroke="var(--color-success)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

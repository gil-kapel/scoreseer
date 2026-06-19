"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ReliabilityBin } from "@/lib/api";

export function ReliabilityChart({ bins }: { bins: ReliabilityBin[] }) {
  const data = bins.map((b) => ({
    bucket: b.bucket,
    Predicted: Math.round(b.avg_confidence * 100),
    Actual: Math.round(b.accuracy * 100),
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis dataKey="bucket" tick={{ fill: "var(--color-fg-muted)", fontSize: 11 }} />
        <YAxis domain={[0, 100]} tick={{ fill: "var(--color-fg-muted)", fontSize: 11 }} unit="%" />
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
        <Bar dataKey="Predicted" fill="var(--color-neutral)" radius={[2, 2, 0, 0]} />
        <Bar dataKey="Actual" fill="var(--color-primary)" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

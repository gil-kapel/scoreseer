import { Card } from "@/components/ui/card";

export function MetricTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card className="p-4">
      <div className="text-xs uppercase tracking-wide text-fg-muted">{label}</div>
      <div className="nums mt-1 text-2xl text-fg">{value}</div>
      {hint ? <div className="mt-0.5 text-xs text-fg-muted">{hint}</div> : null}
    </Card>
  );
}

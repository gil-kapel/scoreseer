import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";

// Status is conveyed by icon + text + color together (color-blind safe — ui-spec).
const MAP: Record<string, { label: string; cls: string; Icon: LucideIcon }> = {
  scheduled: { label: "Scheduled", cls: "text-fg-muted border-border", Icon: Clock },
  running: { label: "Running", cls: "text-info border-info/40", Icon: Loader2 },
  predicted: { label: "Predicted", cls: "text-success border-success/40", Icon: CheckCircle2 },
  failed: { label: "Failed", cls: "text-danger border-danger/40", Icon: XCircle },
  missed: { label: "Missed window", cls: "text-warning border-warning/40", Icon: AlertTriangle },
};

export function StatusChip({ status }: { status: string }) {
  const s = MAP[status] ?? MAP.scheduled;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        s.cls,
      )}
    >
      <s.Icon className={cn("h-3.5 w-3.5", status === "running" && "animate-spin")} />
      {s.label}
    </span>
  );
}

import { cn } from "@/lib/cn";

type Tone = "neutral" | "success" | "danger" | "warning" | "info" | "primary";

const TONES: Record<Tone, string> = {
  neutral: "text-fg-muted border-border",
  success: "text-success border-success/40",
  danger: "text-danger border-danger/40",
  warning: "text-warning border-warning/40",
  info: "text-info border-info/40",
  primary: "text-primary border-primary/40",
};

export function Badge({
  tone = "neutral",
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

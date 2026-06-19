export function fmtKickoff(iso: string): string {
  const d = new Date(iso);
  const s = d.toLocaleString("en-GB", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
  return `${s} UTC`;
}

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

export function fixed(x: number, digits = 2): string {
  return x.toFixed(digits);
}

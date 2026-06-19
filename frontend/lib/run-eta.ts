// Rough per-run-type duration model so the UI can show an estimate + progress.
// Each entry is (fixed overhead, per-fixture seconds). These are deliberate
// approximations — the value is setting expectations, not exact timing.
const ETA: Record<string, { base: number; per: number }> = {
  sync: { base: 25, per: 0 }, // 1 cached API call + grade
  grade: { base: 20, per: 1 }, // mostly stored results
  poisson: { base: 40, per: 0.3 }, // regenerate all + grade + calibrate
  batch_predict: { base: 90, per: 2 }, // submit + poll one Anthropic batch
  batch_backfill: { base: 90, per: 2 },
  predict: { base: 10, per: 90 }, // web search + LLM, sequential per match
  backfill: { base: 10, per: 90 },
};

const DEFAULT = { base: 30, per: 0 };

/** Estimated wall-clock seconds for a run of `type` over `count` fixtures. */
export function etaSeconds(type: string, count = 3): number {
  const e = ETA[type] ?? DEFAULT;
  return Math.round(e.base + e.per * Math.max(1, count));
}

/** Human duration: "45s", "2m", "2m 30s". */
export function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem ? `${m}m ${rem}s` : `${m}m`;
}

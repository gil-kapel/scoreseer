"use client";

import { Clock, Loader2, Play, Square } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { etaSeconds, fmtDuration } from "@/lib/run-eta";

const TYPES = [
  {
    value: "sync",
    label: "Sync + grade",
    hint: "refresh fixture statuses from the sports API + grade finished matches (free)",
  },
  { value: "grade", label: "Grade", hint: "score finished matches (free, no LLM)" },
  {
    value: "baselines",
    label: "Regenerate baselines",
    hint: "rebuild + regrade the free Poisson · Elo · Naive baselines (no Claude)",
  },
  {
    value: "batch_predict",
    label: "Predict upcoming (batch)",
    hint: "cheap forward LLM predictions, no web search — ~$0.005/match",
  },
  { value: "predict", label: "Predict (forward + web)", hint: "real Claude + live web search (pricier)" },
  { value: "backfill", label: "Backfill (past)", hint: "real Claude + web search on played matches" },
  {
    value: "batch_backfill",
    label: "Batch backfill (cheap)",
    hint: "one Anthropic batch, no web search — 50% off, ~$0.005/match",
  },
] as const;

export function RunControls() {
  const router = useRouter();
  const [type, setType] = useState<string>("grade");
  const [count, setCount] = useState<string>("3");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function start() {
    const cheap = type === "batch_backfill" || type === "batch_predict";
    const costly = cheap || type === "predict" || type === "backfill";
    const note = cheap
      ? `A batch makes batched (50%-off) Claude predictions for up to ${count} matches ` +
        "— ~$0.005 each, no web search. Continue?"
      : `A ${type} run makes REAL Claude calls (web search + LLM) for up to ${count} fixtures ` +
        "and incurs API cost. Continue?";
    if (costly && !window.confirm(note)) {
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ type, count: Number(count) || undefined }),
      });
      const data = await res.json();
      setMsg(
        res.ok
          ? { ok: true, text: `Started ${type} run (you can stop it below).` }
          : { ok: false, text: data.detail ?? `error ${res.status}` },
      );
      setTimeout(() => router.refresh(), 800);
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "request failed" });
    } finally {
      setBusy(false);
    }
  }

  const active = TYPES.find((t) => t.value === type);
  const eta = etaSeconds(type, Number(count) || 3);

  return (
    <div className="flex w-full flex-col items-stretch gap-2 md:w-auto md:items-end">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="h-9 flex-1 rounded-md border border-border bg-surface-2 px-2 text-sm text-fg focus:outline-none md:flex-none"
        >
          {TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={1}
          max={104}
          value={count}
          onChange={(e) => setCount(e.target.value)}
          title="how many fixtures (cap)"
          className="h-9 w-16 rounded-md border border-border bg-surface-2 px-2 text-sm text-fg focus:outline-none"
        />
        <Button onClick={start} disabled={busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Start
        </Button>
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-fg-muted md:justify-end">
        <Clock className="h-3 w-3 shrink-0" />
        <span>est. ~{fmtDuration(eta)}</span>
        <span className="text-border">·</span>
        <span>{active?.hint}</span>
      </div>
      {msg ? (
        <div className={`text-xs md:max-w-md md:text-right ${msg.ok ? "text-success" : "text-danger"}`}>
          {msg.text}
        </div>
      ) : null}
    </div>
  );
}

export function StopButton({ runId }: { runId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function stop() {
    setBusy(true);
    await fetch(`/api/runs/${runId}/cancel`, { method: "POST" }).catch(() => {});
    setTimeout(() => router.refresh(), 600);
    setBusy(false);
  }
  return (
    <Button variant="outline" size="sm" onClick={stop} disabled={busy}>
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
      Stop
    </Button>
  );
}

/** Live elapsed timer + progress bar for a running run, so the user can see it's
 *  working and roughly how long it should take. Ticks client-side every second;
 *  the bar approaches (but never reaches) 100% until the run actually finishes. */
export function RunProgress({
  startedAt,
  type,
  count,
}: {
  startedAt: string;
  type: string;
  count?: number;
}) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now()); // first set on mount avoids a server/client clock mismatch
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const eta = etaSeconds(type, count ?? 3);
  const started = new Date(startedAt).getTime();
  const elapsed = now === null ? 0 : Math.max(0, (now - started) / 1000);
  const pct = Math.min(99, (elapsed / eta) * 100);
  const over = elapsed > eta * 1.15;

  return (
    <div className="w-32 space-y-1">
      <div className="flex items-baseline justify-between text-[10px] tabular-nums text-fg-muted">
        <span className="font-medium text-fg">{fmtDuration(elapsed)}</span>
        <span>{over ? "wrapping up…" : `~${fmtDuration(eta)}`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-primary transition-all duration-1000 ease-linear"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** Refreshes the server-rendered runs table while any run is active. */
export function AutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => router.refresh(), 3000);
    return () => clearInterval(id);
  }, [active, router]);
  return null;
}

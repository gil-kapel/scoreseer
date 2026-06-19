"use client";

import { Loader2, Play, Square } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

const TYPES = [
  {
    value: "sync",
    label: "Sync + grade",
    hint: "refresh fixture statuses from the sports API + grade finished matches (free)",
  },
  { value: "grade", label: "Grade", hint: "score finished matches (free, no LLM)" },
  {
    value: "poisson",
    label: "Regenerate Poisson",
    hint: "rebuild + regrade the free Poisson baseline (no Claude)",
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

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-2">
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="h-9 rounded-md border border-border bg-surface-2 px-2 text-sm text-fg focus:outline-none"
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
      <div className="text-[10px] text-fg-muted">{active?.hint}</div>
      {msg ? (
        <div className={`max-w-md text-xs ${msg.ok ? "text-success" : "text-danger"}`}>
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

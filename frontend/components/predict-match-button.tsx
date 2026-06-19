"use client";

import { Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function PredictMatchButton({
  fixtureId,
  predicting = false,
}: {
  fixtureId: string;
  predicting?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const running = busy || predicting;

  async function go() {
    if (
      !window.confirm(
        "Make a REAL Claude prediction for this match (web search + LLM, ~4 min, API cost)?",
      )
    ) {
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/matches/${fixtureId}/predict`, { method: "POST" });
      const data = await res.json();
      setMsg(
        res.ok
          ? "Prediction started — this page now updates itself."
          : (data.detail ?? `error ${res.status}`),
      );
      setTimeout(() => router.refresh(), 1200);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="outline" size="sm" onClick={go} disabled={running}>
        {running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Sparkles className="h-3.5 w-3.5" />
        )}
        {predicting ? "Predicting…" : "Predict this match"}
      </Button>
      {msg ? <span className="max-w-xs truncate text-[10px] text-fg-muted">{msg}</span> : null}
    </div>
  );
}

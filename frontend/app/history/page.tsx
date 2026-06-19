import { Check, X } from "lucide-react";
import Link from "next/link";

import { HistoryFilter } from "@/components/history-filter";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, safe, type HistoryRow } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fmtKickoff } from "@/lib/format";

export const revalidate = 45; // ISR: serve from CDN, refresh in the background

function Row({ r }: { r: HistoryRow }) {
  return (
    <TableRow className={r.is_backfill ? "opacity-55" : undefined}>
      <TableCell className="nums text-xs text-muted-foreground">
        {fmtKickoff(r.kickoff_utc)}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">{r.group_label ?? r.stage}</TableCell>
      <TableCell>
        <Link href={`/matches/${r.fixture_id}`} className="text-sm text-foreground hover:text-primary">
          {r.home} <span className="text-muted-foreground">v</span> {r.away}
        </Link>
        {r.is_backfill ? (
          <span
            className="ml-2 rounded-sm bg-surface-2 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-warning"
            title="Predicted after the match (hindsight) — excluded from accuracy & calibration"
          >
            backfill
          </span>
        ) : null}
      </TableCell>
      <TableCell className="nums text-sm text-muted-foreground">{r.predicted}</TableCell>
      <TableCell className="nums text-sm font-medium text-foreground">{r.actual}</TableCell>
      <TableCell>
        <span
          className={cn(
            "inline-flex items-center gap-1 text-xs",
            r.exact_hit ? "text-success" : r.outcome_correct ? "text-warning" : "text-danger",
          )}
        >
          {r.outcome_correct ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
          {r.exact_hit ? "Exact" : r.outcome_correct ? "Outcome" : "Miss"}
        </span>
      </TableCell>
      <TableCell className="nums text-right text-sm font-medium text-primary">
        {r.points > 0 ? `+${r.points}` : "0"}
      </TableCell>
    </TableRow>
  );
}

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<{ outcome?: string }>;
}) {
  const sp = await searchParams;
  const qs = new URLSearchParams({ limit: "200" });
  if (sp.outcome) qs.set("outcome", sp.outcome);
  const { data, error } = await safe(api.history(qs.toString()));

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">History</h1>
          <p className="text-sm text-muted-foreground">Graded matches — prediction vs actual.</p>
        </div>
        <HistoryFilter value={sp.outcome ?? "all"} />
      </header>

      {error ? (
        <Card className="p-6 text-sm text-danger">Couldn&apos;t load history: {error}</Card>
      ) : !data || data.length === 0 ? (
        <Card className="p-6 text-sm text-muted-foreground">No graded matches yet.</Card>
      ) : (
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Kickoff</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Match</TableHead>
                <TableHead>Pred</TableHead>
                <TableHead>Actual</TableHead>
                <TableHead>Grade</TableHead>
                <TableHead className="text-right">Pts</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((r) => (
                <Row key={r.fixture_id} r={r} />
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

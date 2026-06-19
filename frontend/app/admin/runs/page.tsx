import { AutoRefresh, RunControls, RunProgress, StopButton } from "@/components/run-controls";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, safe, type RunRead } from "@/lib/api";
import { fmtKickoff } from "@/lib/format";

export const dynamic = "force-dynamic";

function statusTone(status: string) {
  if (status === "succeeded") return "success" as const;
  if (status === "partial") return "warning" as const;
  if (status === "failed") return "danger" as const;
  if (status === "cancelled") return "neutral" as const;
  return "info" as const; // running
}

function RunRow({ run }: { run: RunRead }) {
  const t = run.totals as { succeeded?: number; skipped?: number; failed?: number };
  const running = run.status === "running";
  const cap = typeof run.params?.cap === "number" ? (run.params.cap as number) : undefined;
  return (
    <TableRow>
      <TableCell className="text-sm text-foreground">{run.type}</TableCell>
      <TableCell className="hidden text-xs text-muted-foreground md:table-cell">
        {run.trigger}
      </TableCell>
      <TableCell>
        <Badge tone={statusTone(run.status)}>{run.status}</Badge>
      </TableCell>
      <TableCell className="nums hidden text-xs text-muted-foreground md:table-cell">
        {fmtKickoff(run.started_at)}
      </TableCell>
      <TableCell className="nums text-xs text-muted-foreground">
        {running ? (
          <RunProgress startedAt={run.started_at} type={run.type} count={cap} />
        ) : (
          <span>
            {t.succeeded ?? 0}✓ · {t.skipped ?? 0} skip · {t.failed ?? 0}✗
          </span>
        )}
      </TableCell>
      <TableCell className="text-right">
        {running ? <StopButton runId={run.id} /> : null}
      </TableCell>
    </TableRow>
  );
}

export default async function AdminRunsPage() {
  const { data, error } = await safe(api.runs());
  const anyRunning = !!data?.some((r) => r.status === "running");

  return (
    <div className="space-y-6">
      <AutoRefresh active={anyRunning} />
      <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Runs</h1>
          <p className="max-w-lg text-sm text-muted-foreground">
            Predict = real Claude on upcoming matches (forward). Grade = score finished matches
            (free). Backfill = real Claude on played matches (labeled, excluded from accuracy).
          </p>
        </div>
        <RunControls />
      </header>

      {error ? (
        <Card className="p-6 text-sm text-danger">Couldn&apos;t load runs: {error}</Card>
      ) : !data || data.length === 0 ? (
        <Card className="p-6 text-sm text-muted-foreground">No runs yet. Start one above.</Card>
      ) : (
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Type</TableHead>
                <TableHead className="hidden md:table-cell">Trigger</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">Started</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

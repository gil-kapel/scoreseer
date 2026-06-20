import { Network } from "lucide-react";

import { ForecastBoard } from "@/components/forecast-board";
import { Card } from "@/components/ui/card";
import { api, safe } from "@/lib/api";

export const revalidate = 45;

export default async function ForecastPage() {
  const { data, error } = await safe(api.upcoming(336));
  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-fg">
          <Network className="h-5 w-5 text-primary" /> Forecast
        </h1>
        <p className="text-sm text-fg-muted">
          Upcoming matches ranked by win-probability — drag the filter to surface only the
          confident calls (the &ldquo;most likely path&rdquo;).
        </p>
      </header>
      {error ? (
        <Card className="p-6 text-sm text-danger">Couldn&apos;t load forecast: {error}</Card>
      ) : (
        <ForecastBoard fixtures={data ?? []} />
      )}
    </div>
  );
}

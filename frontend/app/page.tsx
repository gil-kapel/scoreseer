import { FixtureCard, FixtureListHeader } from "@/components/fixture-card";
import { Card } from "@/components/ui/card";
import { api, safe, type FixtureRead } from "@/lib/api";

export const revalidate = 45; // ISR: serve from CDN, refresh in the background

function groupByDate(fixtures: FixtureRead[]): [string, FixtureRead[]][] {
  const groups = new Map<string, FixtureRead[]>();
  for (const f of fixtures) {
    const day = f.kickoff_utc.slice(0, 10);
    (groups.get(day) ?? groups.set(day, []).get(day)!).push(f);
  }
  return [...groups.entries()];
}

export default async function UpcomingPage() {
  const { data, error } = await safe(api.upcoming(168));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-fg">Upcoming</h1>
        <p className="text-sm text-fg-muted">
          Fixtures in the next 7 days and their prediction status.
        </p>
      </header>

      {error ? (
        <Card className="p-6 text-sm text-danger">Couldn&apos;t load fixtures: {error}</Card>
      ) : !data || data.length === 0 ? (
        <Card className="p-6 text-sm text-fg-muted">
          No matches in the prediction window yet.
        </Card>
      ) : (
        <div className="space-y-3">
          <FixtureListHeader />
          <div className="space-y-6">
            {groupByDate(data).map(([day, fixtures]) => (
              <section key={day} className="space-y-2">
                <h2 className="nums text-xs font-medium uppercase tracking-wide text-fg-muted">
                  {day}
                </h2>
                <div className="space-y-2">
                  {fixtures.map((f) => (
                    <FixtureCard key={f.id} fixture={f} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

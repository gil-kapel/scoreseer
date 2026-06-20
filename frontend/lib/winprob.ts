export type Split = { home: number; draw: number; away: number };

/**
 * Derive a 3-way win/draw/win split from a predicted scoreline + outcome confidence.
 * The estimators compute the exact split server-side; this is the display
 * approximation the UI uses until it's persisted. Confidence = P(predicted outcome);
 * the remainder is shared between the other two outcomes (underdog win a touch more
 * likely than a draw for a decisive prediction).
 */
export function deriveSplit(homeScore: number, awayScore: number, confidence: number): Split {
  const c = Math.min(0.95, Math.max(0.34, confidence || 0.4));
  const rest = 1 - c;
  if (homeScore > awayScore) return { home: c, draw: rest * 0.45, away: rest * 0.55 };
  if (homeScore < awayScore) return { home: rest * 0.55, draw: rest * 0.45, away: c };
  return { home: rest * 0.5, draw: c, away: rest * 0.5 };
}

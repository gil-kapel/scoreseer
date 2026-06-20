// Server-side API client. Talks to the FastAPI backend over the internal
// Docker network (API_BASE=http://backend:8000) — no CORS, no browser secrets.

import { API_BASE, backendHeaders } from "@/lib/backend";

export type TeamBrief = {
  code: string;
  name: string;
  group_label: string | null;
  crest_url: string | null;
};

export type ScorerPred = { player_name: string; team: "home" | "away"; likelihood: number };

export type PredictionSummary = {
  home_score: number;
  away_score: number;
  match_confidence: number;
  scorers: ScorerPred[];
};

export type FixtureRead = {
  id: string;
  external_id: string;
  provider: string;
  stage: string;
  group_label: string | null;
  home: TeamBrief;
  away: TeamBrief;
  kickoff_utc: string;
  venue: string | null;
  status: string;
  prediction_status: string;
  prediction: PredictionSummary | null;
};

export type PredictionRead = {
  id: string;
  home_score: number;
  away_score: number;
  scorers: ScorerPred[];
  match_confidence: number;
  advancing_team: "home" | "away" | null;
  explanation: string;
  status: string;
  failure_reason: string | null;
  model_id: string;
  prompt_version: string;
  calibration_version: number;
  is_backfill: boolean;
  created_at: string;
};

export type ResultRead = {
  home_score_90: number;
  away_score_90: number;
  ft_outcome: string;
  decided_by: string;
  scorers: { player_name: string; team: string; type: string; minute?: number }[];
  status: string;
};

export type GradeRead = {
  exact_hit: boolean;
  outcome_correct: boolean;
  goals_abs_error: number;
  scorer_precision: number;
  scorer_recall: number;
  scorer_brier: number;
  confidence_brier: number;
  advancing_correct: boolean | null;
  points: number;
};

export type MatchDetail = {
  fixture: FixtureRead;
  prediction: PredictionRead | null;
  estimators: PredictionRead[];
  result: ResultRead | null;
  grade: GradeRead | null;
  sources: { url: string; title: string | null }[];
  data_quality: string | null;
  predicting: boolean;
};

export type TrendPoint = {
  date: string;
  n: number;
  cumulative_outcome: number;
  cumulative_exact: number;
  cumulative_points: number;
};

export type StagePoints = {
  stage: string;
  points: number;
  max_points: number;
  n: number;
};

export type DashboardMetrics = {
  n_graded: number;
  outcome_accuracy: number;
  exact_rate: number;
  goals_mae: number;
  scorer_precision: number;
  scorer_recall: number;
  confidence_brier: number;
  total_points: number;
  max_points: number;
  points_by_stage: StagePoints[];
  backfill_excluded: number;
  trend: TrendPoint[];
};

export type EstimatorStats = {
  estimator: string;
  n_graded: number;
  outcome_accuracy: number;
  exact_rate: number;
  goals_mae: number;
  confidence_brier: number;
  total_points: number;
  max_points: number;
};

export type InsightItem = {
  fixture_id: string;
  home: string;
  away: string;
  kickoff_utc: string;
  predicted: string;
  confidence: number;
  explanation: string;
  model_id: string;
  created_at: string;
  played: boolean;
};

export type ReliabilityBin = { bucket: string; avg_confidence: number; accuracy: number; n: number };
export type CalibrationVersion = {
  version: number;
  computed_at: string;
  n_graded: number;
  bias_summary: string;
};
export type CalibrationView = {
  current: CalibrationVersion | null;
  prompt_snippet: string | null;
  metric_aggregates: Record<string, number>;
  versions: CalibrationVersion[];
  reliability: ReliabilityBin[];
  first_half_brier: number | null;
  second_half_brier: number | null;
};

export type HistoryRow = {
  fixture_id: string;
  home: string;
  away: string;
  stage: string;
  group_label: string | null;
  kickoff_utc: string;
  predicted: string;
  actual: string;
  exact_hit: boolean;
  outcome_correct: boolean;
  goals_abs_error: number;
  points: number;
  is_backfill: boolean;
};

export type RunRead = {
  id: string;
  type: string;
  trigger: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  params: Record<string, unknown>;
  totals: Record<string, unknown>;
};
export type RunItemRead = { fixture_id: string; status: string; detail: string | null };
export type RunDetail = { run: RunRead; items: RunItemRead[] };

// `revalidate` (seconds) caches the response server-side so most page loads serve
// from Vercel's CDN instead of hitting the backend (US) -> Neon (Frankfurt) every
// time — this also masks Render free-tier cold starts. Pass `false` for live data.
async function get<T>(path: string, revalidate: number | false = 45): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: backendHeaders(),
    ...(revalidate === false ? { cache: "no-store" } : { next: { revalidate } }),
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  base: API_BASE,
  // Slow-changing reads — cached ~45s (ISR).
  upcoming: (windowH = 336) => get<FixtureRead[]>(`/api/fixtures/upcoming?window_h=${windowH}`),
  metrics: () => get<DashboardMetrics>(`/api/dashboard/metrics`),
  estimators: () => get<EstimatorStats[]>(`/api/dashboard/estimators`),
  insights: (limit = 40) => get<InsightItem[]>(`/api/dashboard/insights?limit=${limit}`),
  calibration: () => get<CalibrationView>(`/api/dashboard/calibration`),
  history: (qs: string) => get<HistoryRow[]>(`/api/history${qs ? `?${qs}` : ""}`),
  // Live reads — never cached (run status, in-flight prediction indicator).
  matchDetail: (id: string) => get<MatchDetail>(`/api/matches/${id}`, false),
  runs: () => get<RunRead[]>(`/api/admin/runs`, false),
};

export async function safe<T>(p: Promise<T>): Promise<{ data: T | null; error: string | null }> {
  try {
    return { data: await p, error: null };
  } catch (e) {
    return { data: null, error: e instanceof Error ? e.message : "request failed" };
  }
}

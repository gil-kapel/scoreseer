# PRD: ScoreSeer — World Cup 2026 Match Result Estimator

> Working title. A personal "accuracy lab" that predicts exact football results (final score, likely scorers, and reasoning) for FIFA World Cup 2026, then grades itself against reality and calibrates over time.

## Summary

ScoreSeer automatically predicts upcoming World Cup 2026 fixtures. For each match it fetches fresh context via Claude web search (form, lineups, injuries, head-to-head, odds, venue), runs an estimator that injects the system's own past accuracy as calibration, and asks an LLM to return a **structured prediction**: exact final score, named goalscorers with likelihoods, a confidence level, and a short explanation. After each match finishes it fetches the real result, grades the prediction, and updates accuracy metrics that flow back into future predictions. A web UI shows upcoming predictions, graded history, and an accuracy trend over the tournament.

The product's north star is not "win bets" — it is **measurable, improving prediction accuracy across the tournament**, with full reproducibility of why each prediction was made.

## Problem

Predicting exact football scores is hard, and most casual prediction happens with no feedback loop: you guess, the match happens, and you never systematically learn whether your reasoning was good. There is no personal tool that (a) gathers the relevant pre-match signals automatically, (b) commits to a falsifiable, structured prediction, and (c) scores itself honestly and uses that score to get better.

Who feels the pain: the builder — a technically-capable football fan who wants a rigorous, self-improving prediction system and a clean record of how well it's doing, rather than vibes-based guessing.

Why existing behavior isn't good enough:
- Manual prediction has no persistent accuracy ledger and no calibration.
- Pundit predictions and bookmaker odds aren't structured, reproducible, or self-grading.
- Generic LLM "predict this match" prompts hallucinate, don't cite data, and never learn from being wrong.

What success looks like: by the end of the tournament, ScoreSeer has a complete prediction-vs-result ledger, a visible accuracy trend, and demonstrable improvement in calibration as more matches are graded.

## Target users

**Primary user — "The Analyst" (the builder).**
- Goal: make rigorous, structured predictions for every World Cup 2026 match and watch the system's accuracy improve.
- Context: solo, low-frequency interaction (checks in around matchdays), comfortable with technical detail, runs it for themselves.
- Device: desktop web primarily; mobile-readable.
- Permission: single-user / owner. No multi-tenant accounts in MVP.

Secondary stakeholders: none in MVP (no public users, no sharing). Designed so a read-only public view *could* be added later.

## Goals and success metrics

Primary goal: a self-grading, self-calibrating prediction system whose accuracy is tracked and trends upward over the tournament.

Success metrics (measured across all graded WC2026 matches):
- **Outcome accuracy (1/X/2):** ≥ 55% of matches' result direction predicted correctly by end of tournament.
- **Exact-score hit rate:** ≥ 12% of matches' exact 90-minute score predicted correctly (baseline: blind guessing is ~5–8%; bookmaker-implied "most likely score" lands ~10–14%).
- **Total-goals error:** mean absolute error of total goals ≤ 1.3.
- **Scorer quality:** named-goalscorer recall ≥ 35% (of actual scorers, fraction we listed) with precision tracked; per-player likelihoods evaluated by Brier score, trending down.
- **Confidence calibration:** match-level confidence is calibrated — Brier score of the system's win/draw probabilities improves in the tournament's second half vs the first half (evidence the calibration loop works).
- **Operational:** ≥ 95% of scheduled fixtures get a prediction before kickoff and a grade within 24h of full-time.

These are targets for steering, not contractual guarantees — exact-score prediction is inherently low-hit-rate.

## In scope

- FIFA World Cup 2026 fixtures only (group + knockout stages).
- Scheduled auto-run that predicts upcoming fixtures ahead of kickoff.
- Claude web search data fetch per fixture, with the fetched evidence stored as an immutable snapshot.
- LLM structured prediction: exact final score, named goalscorers + per-player likelihood, match confidence, and a short natural-language explanation citing the key signals.
- Auto-grading after full-time: fetch real result + scorers, compare, compute metrics.
- Calibration loop: accumulated accuracy/calibration stats injected into future prediction prompts ("track + calibrate", no trained ML model in MVP).
- Web UI (read-focused): upcoming predictions, graded history per match, and an accuracy-trend dashboard.
- Single-user / owner-only.

## Out of scope

- Other leagues or sports (data model should generalize, but only WC2026 ships).
- Live / in-play prediction updates during a match.
- Betting integration, stake sizing, odds-shopping, or any wagering features.
- Multi-user accounts, auth providers, social/leaderboard, sharing.
- A trained statistical/ML model (Poisson, regression) — explicitly deferred; MVP calibrates via prompt only.
- Mobile native app.
- Guaranteeing accuracy thresholds (targets only).
- Manual on-demand "predict any random match" UX as the primary flow (scheduled auto-run is primary; a manual re-run trigger is allowed as an admin convenience).

## Main user flow

The core "actor" is the **scheduler**; the human mostly observes. Two flows run per fixture.

**A. Prediction flow (before kickoff)**
1. **Entry point:** Scheduler wakes on a cadence (e.g. daily) and selects fixtures kicking off within the prediction window (e.g. next 12–36h) that don't yet have a prediction.
2. **Data fetch:** For each fixture, Claude web search gathers pre-match context — recent form, probable/announced lineups, injuries & suspensions, head-to-head, group standings / knockout stakes, venue, and (optionally) bookmaker odds. The raw evidence + source references are saved as an immutable **DataSnapshot**.
3. **Estimate (branch):** The estimator assembles the snapshot into a structured context and injects the current **CalibrationProfile** (the system's recent accuracy and known biases, e.g. "you over-predict home/favourite blowouts by ~0.4 goals"). Stage-specific rules apply (group stage allows draws; knockout "exact score" is defined as the 90-minute scoreline — see Open Questions).
4. **Predict:** The LLM returns a validated structured **Prediction**: final score, list of likely scorers each with a likelihood, an overall match confidence, and a concise explanation referencing the strongest signals.
5. **Result (success state):** Prediction is stored, linked to its DataSnapshot and the model/prompt version, and appears in the UI under "Upcoming."
6. **Failure / edge state:** If web search yields thin/conflicting data, the prediction is still produced but flagged low-confidence with a "data quality" note. If the LLM output fails schema validation, retry with a repair prompt; after N failures, mark the fixture "prediction failed" (visible, not silent).

**B. Grading flow (after full-time)**
7. **Entry point:** Scheduler detects a predicted match has finished.
8. **Result fetch:** Claude web search retrieves the final score and goalscorers; saved as a **Result**.
9. **Grade:** Compare prediction vs result → exact-score hit (y/n), outcome correct (y/n), total-goals error, scorer precision/recall, scorer-likelihood Brier, confidence Brier. Persist a **Grade**.
10. **Calibrate:** Recompute the CalibrationProfile from the rolling Grade history so the next predictions account for observed bias.
11. **Edge state:** Match postponed/abandoned → mark **void** (excluded from metrics). Knockout went to ET/penalties → grade exact-score on the 90-minute line, record the ET/pen outcome separately for the outcome metric.

## Functional requirements

Prediction
- The system must select eligible upcoming WC2026 fixtures within a configurable prediction window and avoid duplicate predictions for the same fixture+model version.
- The system must fetch pre-match context via Claude web search and persist the evidence and its source references as an immutable DataSnapshot tied to the prediction.
- The system must inject the current CalibrationProfile into the prediction context.
- The system must produce a Prediction conforming to a strict schema: `home_score:int`, `away_score:int`, `scorers:[{player, team, likelihood 0–1}]`, `match_confidence:0–1`, `explanation:string`, plus model/prompt version and timestamps.
- The system must validate LLM output against the schema and retry with a repair prompt on failure, capping retries and recording a visible failure if unresolved.
- The system must respect stage rules: group predictions may be draws; knockout predictions represent the 90-minute scoreline and additionally indicate the predicted advancing team.

Grading & calibration
- The system must detect finished predicted matches and fetch the real final score and goalscorers via web search, stored as a Result.
- The system must compute and persist per-match Grades (exact-score hit, outcome correct, total-goals abs error, scorer precision/recall, scorer Brier, confidence Brier).
- The system must recompute the CalibrationProfile from rolling Grade history after each grading run.
- The system must mark postponed/abandoned matches void and exclude them from accuracy metrics.

Web UI
- The UI must list upcoming fixtures with their predictions (score, scorers + likelihoods, confidence, explanation).
- The UI must show a per-match detail view comparing prediction vs actual result with the computed grade and the source evidence used.
- The UI must show a tournament accuracy dashboard (outcome accuracy, exact-score rate, goals MAE, calibration trend over time).
- The UI must allow the owner to manually trigger a (re-)prediction or a grading run for a fixture (admin convenience).

System / data
- The system must store every prediction with enough provenance (snapshot, model id, prompt version, calibration version) to reproduce/explain it after the fact.
- The system must be single-user; no public write access.

## Non-functional requirements

- **Reproducibility:** every prediction is reconstructable from stored snapshot + versions. Predictions are append-only (re-runs create new versioned records, never overwrite).
- **Cost control:** web search + LLM calls are batched per scheduler run and bounded per fixture; configurable caps prevent runaway spend. (Cost not a top constraint, but must be observable.)
- **Latency:** non-interactive; a scheduler run completing within minutes is fine. UI reads must render < 1s from stored data (no live LLM calls on page load).
- **Reliability:** a failure on one fixture must not abort the batch; failures are logged and visible in the UI.
- **Data freshness:** lineup/injury data should be fetched close to kickoff (within the prediction window) so late team news is captured.
- **Auditability:** source references for both predictions and results are stored and viewable.
- **Privacy/legal:** no wagering features; results data is sourced from public web search with references retained.

## Acceptance criteria

- **Eligible-fixture selection:** Given fixtures with various kickoff times, when the scheduler runs, then only fixtures inside the prediction window without an existing current-version prediction are selected. Pass = no duplicates, no out-of-window fixtures.
- **Snapshot persisted:** Given a prediction run, when data is fetched, then a DataSnapshot with non-empty evidence and ≥1 source reference exists and is linked to the Prediction. Pass = snapshot retrievable from the prediction detail view.
- **Schema-valid prediction:** Given any completed prediction, when stored, then it validates against the Prediction schema with `0 ≤ likelihood ≤ 1` and `0 ≤ match_confidence ≤ 1`. Pass = 100% of stored predictions validate.
- **Repair on bad output:** Given an LLM response that fails validation, when the system retries, then it either produces a valid prediction within N retries or records a visible "prediction failed" state. Pass = no silent drops.
- **Grading correctness:** Given a finished match with known result, when graded, then exact-score hit, outcome correctness, and total-goals error match a hand-computed reference for a test fixture. Pass = computed metrics equal reference values.
- **Knockout handling:** Given a knockout match decided in ET/penalties, when graded, then exact-score is graded on the 90-minute line and the advancing-team outcome is recorded separately. Pass = both fields populated correctly.
- **Void handling:** Given a postponed/abandoned match, when grading runs, then it is marked void and excluded from all accuracy aggregates. Pass = void match absent from dashboard metrics.
- **Calibration updates:** Given new Grades, when calibration recomputes, then the CalibrationProfile version increments and subsequent prediction prompts include the updated profile. Pass = prompt log shows current profile version.
- **Dashboard integrity:** Given a set of graded matches, when the dashboard renders, then aggregate metrics equal the aggregation of stored Grades (excluding voids). Pass = UI numbers reconcile with the data store.
- **Resilience:** Given one fixture's fetch throws, when the batch runs, then remaining fixtures still complete and the failure is visible. Pass = batch completion with logged per-fixture failure.

## Risks

- **Product risk (medium):** Exact-score prediction has an intrinsically low hit rate; the system may look "wrong" a lot even when reasoning is sound. Mitigation: lead with outcome accuracy + calibration trend, not exact-score hit rate, as the primary success signal.
- **Product risk (medium):** "Improves over time" via prompt-only calibration may show weak or noisy improvement over just ~104 matches. Mitigation: track calibration explicitly (Brier first-half vs second-half) and be honest if the loop doesn't move the needle; ML model is the deferred fallback.
- **UX risk (low–medium):** A scheduler-driven app with little human action can feel "empty"; the value is in the history/trend views, which must be compelling from match one. Mitigation: strong dashboard + match-detail evidence views.
- **Technical risk (high):** Web search data can be stale, conflicting, or sparse (esp. late lineup/injury news); result/scorer fetching can be wrong or delayed. Mitigation: store source references, flag low-data predictions, allow manual re-grade, prefer near-kickoff fetch.
- **Technical risk (medium):** LLM structured-output reliability — malformed or hallucinated scorers. Mitigation: strict schema + repair-retry + visible failure state.
- **Delivery risk (medium):** Tournament is **time-boxed and already underway (group stage, ~June 2026)** — every day of delay loses gradable matches and shrinks the calibration dataset. Mitigation: ship the prediction+storage+grading core first; the dashboard polish can trail.
- **Information gaps (see open questions):** exact-score baseline for knockouts, whether to use bookmaker odds as a signal, and web-search result reliability are the biggest confidence-blockers.

## Open questions

1. **Knockout "exact score" definition** — Default proposed: grade exact-score on the **90-minute** scoreline, track ET/penalties only for the advancing-team outcome. Confirm this is the desired convention.
2. **Bookmaker odds as input** — Should pre-match odds be a fetched signal (improves calibration but may anchor the LLM to the market and reduce independent value)? Default: fetch but clearly label, and log predictions both with and without if cheap.
3. **Prediction window & cadence** — How far before kickoff to predict (12h? 36h?) and how often the scheduler runs. Trade-off: earlier = stale lineups; later = risk of missing the window. Default: run daily, predict fixtures within next ~24h, re-fetch lineups if available closer to kickoff.
4. **Result/scorer source of truth** — Is web search alone trustworthy for final scores & scorers, or should a structured fixtures/results data source be used for grading (web search for narrative, structured source for ground truth)? Affects grading reliability and is the single biggest data-integrity question.
5. **Scorer matching** — How to credit "named goalscorers" (own goals? penalties? exact name string vs fuzzy match)? Default: match on player identity, count penalties as goals, exclude own goals from scorer predictions but record them for total-goals.
6. **Calibration signal strength** — Is prompt-only calibration enough, or should we plan the lightweight Poisson/ML model as a fast-follow if calibration doesn't improve?

## Handoff to architecture / UX

**Likely entities / data objects**
- `Fixture` (id, stage, group, home_team, away_team, kickoff_utc, venue, status)
- `Team`, `Player` (squad reference for scorer validation)
- `DataSnapshot` (fixture_id, fetched_at, evidence payload, source_refs[], search query log)
- `Prediction` (fixture_id, snapshot_id, home_score, away_score, scorers[{player, team, likelihood}], match_confidence, advancing_team?, explanation, model_id, prompt_version, calibration_version, created_at)
- `Result` (fixture_id, home_score_90, away_score_90, ft_outcome, scorers[], decided_by[regular/ET/pens], source_refs[], status[final/void])
- `Grade` (prediction_id, exact_hit, outcome_correct, goals_abs_error, scorer_precision, scorer_recall, scorer_brier, confidence_brier)
- `CalibrationProfile` (version, computed_at, bias_summary, metric_aggregates, prompt_snippet)

**Screens / surfaces likely needed**
- Upcoming predictions list
- Match detail (prediction vs result + evidence + grade)
- Accuracy dashboard (trends, calibration)
- Admin: trigger predict/grade, view failures, config (window, cadence, caps)

**Roles / permissions**
- Single owner (full read/write). Optional future: public read-only.

**External integrations mentioned**
- Claude API with web search (data fetch + result fetch).
- Claude API for structured-output prediction (use strict schema / tool-use; consider an explicit results data source per Open Question 4).
- A scheduler (cron) for prediction and grading runs.
- A datastore for append-only predictions/snapshots/grades.

**Suggested architecture questions to resolve**
- Where does the scheduler run (cron service vs hosted scheduler) and how are runs made idempotent/resumable?
- Web search vs a structured fixtures/results API for ground-truth grading (Open Q4).
- How is the Prediction schema enforced (tool-use / structured output) and versioned alongside the prompt?
- Storage choice for append-only, reproducible records (relational with JSON columns is the natural fit).
- How is the CalibrationProfile computed and turned into a compact prompt snippet without bloating context?
- Cost observability and per-run caps.

---

*Next agents:* UX (`/ux-user-flow-agent`) to design the observe-focused flows and states, then UI (`/ui-design-systems-agent`), then architecture (`/tech-lead-architecture-agent`), then implementation slices (`/dev-composer-agent`).

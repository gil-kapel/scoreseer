# UX Flow: ScoreSeer — World Cup 2026 Estimator

> Builds on [docs/prd.md](prd.md). This document is **flow logic and states only** — no visual design (that's the UI agent's job).
>
> **Key UX framing:** the scheduler is the protagonist; the human is an *observer/auditor*. So the product's job is not "help me complete a task" but "let me trust, inspect, and watch the system get better." Every screen must answer one of: *What will it predict? Was it right? Is it improving? What's broken?*
>
> **Assumptions made** (flagged, not blocking — confirm if wrong): single owner accesses via a private deploy with light auth; routes below are proposals for the architecture agent to ratify; timezone shown in the user's local time with UTC on hover.

## User and goal

- **User:** The Analyst (the builder / single owner).
- **Trigger:** Mostly time/event-driven — a matchday approaches, or the user idly checks in. Secondarily, the user manually triggers a predict/grade run.
- **Goal:** See upcoming predictions, verify past predictions against reality, and watch accuracy/calibration trend over the tournament — with the ability to inspect *why* any prediction was made and to fix anything that broke.
- **Success condition:** User can, in under a minute, answer "what's predicted next, how are we doing, and is anything broken?" and drill into the evidence behind any single prediction.
- **Failure condition:** User can't tell whether a missing prediction is "not yet due," "still running," or "failed"; or the accuracy numbers can't be trusted/reconciled.

## Roles and permissions

Single-role MVP, but two *modes* matter for state design (read vs. admin actions).

| Role | Can view | Can act | Gated by |
|------|----------|---------|----------|
| Owner | All predictions, results, evidence, grades, dashboard, run logs/failures, config | Trigger predict run, trigger grade run, re-run a fixture, edit config (window/cadence/caps), mark match void, retry failed run | Owner session (private deploy) |
| Public (future, out of MVP scope) | Read-only predictions + dashboard | — | Feature flag |

Destructive/spendy actions (re-run prediction = new LLM+search spend; mark void = excludes from metrics) require explicit confirmation — see edge paths.

## Main journey (observe path — the 90% case)

1. **Entry → Home / Upcoming.** User opens the app and lands on **Upcoming Predictions**. Each upcoming fixture shows a status chip: `Predicted`, `Scheduled (predicts in ~Xh)`, `Running…`, or `Failed`.
2. **Scan upcoming.** User reads predicted scorelines, top scorers, and confidence at a glance, ordered by kickoff. A persistent header strip shows tournament-level accuracy (outcome %, exact-score %, calibration arrow ↑/↓).
3. **Drill into a match.** User clicks a fixture → **Match Detail**. Sees the prediction (score, scorers + likelihoods, confidence, explanation) and, if the match is finished, the **actual result side-by-side with the grade**, plus the **evidence/sources** the prediction was built from.
4. **Confirmation of "why."** Evidence panel shows the fetched signals (form, lineups, injuries, H2H, odds) with source links and the model/prompt/calibration version — the user trusts the prediction because it's auditable.
5. **Check the trend.** User goes to **Accuracy Dashboard** to see metrics over time and the calibration story (first-half vs second-half Brier, current bias summary).
6. **Return path.** Back to Upcoming. If something showed `Failed`, the user can branch to the admin recovery sub-flow.

> Happy path is 6 steps and fully observational. No required human action for the system to function.

### Sub-flow A: Manual predict/grade (admin convenience)
1. From Match Detail or Admin/Runs, user clicks **Predict now** / **Grade now** / **Re-run**.
2. Confirmation dialog (states spend implication for predict/re-run).
3. Run kicks off → fixture shows `Running…` with live-ish status.
4. On success → prediction/grade appears (announced). On failure → `Failed` with reason + Retry.

### Sub-flow B: Recover a failed run
1. From Upcoming chip `Failed` or Admin/Runs failures list, user opens the failed run.
2. Sees failure reason (e.g. "schema validation failed after 3 retries", "web search returned no sources", "result not found yet").
3. Chooses **Retry**, **Mark void** (if abandoned), or **Edit config & retry**.

## Failure and edge paths

| Branch point | Condition | Behavior + message |
|--------------|-----------|--------------------|
| Upcoming list | No fixtures in window yet | Empty state (see states). Not an error. |
| Prediction | Web search returns thin/conflicting data | Prediction still produced, flagged **Low data quality** badge: "Predicted with limited pre-match data — confidence reduced." Evidence panel notes which signals were missing. |
| Prediction | LLM output fails schema after N retries | Fixture = `Failed`. Match Detail shows: "Prediction failed: response didn't match the required format after 3 attempts." Actions: Retry, View raw output (admin). |
| Prediction | Run window passed before predict ran (kickoff imminent/started) | Fixture = `Missed window`: "Not predicted before kickoff." No retry for prediction; can still grade after. |
| Grading | Result not yet available | `Awaiting result` (not failure): "Match finished — fetching result." Auto-retries; manual **Grade now** available. |
| Grading | Result sources conflict | `Result needs review`: "Conflicting final scores from sources — review before grading." Shows candidate results + sources; owner confirms ground truth. |
| Grading | Match postponed/abandoned | Owner can **Mark void**: "Excluded from accuracy metrics." Reversible. |
| Knockout | Decided in ET/penalties | Detail shows 90-min line graded for exact-score + a separate "Advanced: {team} (pens)" outcome row. Tooltip explains the convention. |
| Manual run | User triggers re-run on an already-predicted fixture | Confirm: "This creates a new prediction version and incurs API/search cost. The previous version is kept. Continue?" Cancel / Confirm. |
| Any run | Network/API timeout | Inline error toast + run marked `Failed` with reason; batch continues for other fixtures. "Run failed for {match}: {reason}. Other fixtures unaffected." |
| Config | Invalid value (e.g. window = 0h, negative cap) | Block save, inline message per field (see validation table). |
| Navigation | User leaves mid-run | Runs are server-side; leaving is safe. On return, status reflects current run state. No data loss, no confirm needed. |
| Mark void / config save | Destructive/impactful | Require explicit confirm; void is reversible ("Restore to active"). |

## Screen inventory

| Screen | Route (proposed) | Purpose | Primary action | Secondary action | Required data |
|--------|------------------|---------|----------------|------------------|---------------|
| Upcoming Predictions (Home) | `/` | See what's predicted next + tournament health strip | Open match detail | Trigger predict run | Fixtures in window, their prediction status, header metrics |
| Match Detail | `/matches/[fixtureId]` | Inspect one prediction vs result + evidence + grade | (read) | Predict/Grade/Re-run, Mark void | Fixture, Prediction(+versions), Result, Grade, DataSnapshot |
| Results / History | `/history` | Browse graded past matches, filter by stage/outcome | Open match detail | Filter/sort | Graded predictions + results |
| Accuracy Dashboard | `/dashboard` | Trends + calibration story | (read) | Toggle metric / date range | Aggregated Grades, CalibrationProfile history |
| Admin · Runs | `/admin/runs` | Monitor scheduler runs, failures, retries | Retry failed | Trigger run, view logs | Run records, per-fixture outcomes, failures |
| Admin · Config | `/admin/config` | Set window, cadence, spend caps, signals (e.g. odds on/off) | Save config | Reset to defaults | Config object |
| Calibration Detail (optional, can live in Dashboard) | `/dashboard/calibration` | Current bias summary + version history | (read) | Compare versions | CalibrationProfile versions |

## States by screen

**Upcoming Predictions (`/`)**
- *Empty (no fixtures in window):* "No matches in the prediction window yet. Next fixture: {team v team}, {date}. Predictions are generated ~{window}h before kickoff." Show next scheduler run time.
- *Empty (tournament not started / over):* "World Cup 2026 group stage hasn't reached the window" / "Tournament complete — see the dashboard for the final accuracy report."
- *Loading:* skeleton rows for fixture cards; header metrics show shimmer.
- *Populated:* fixture cards with status chips + header accuracy strip.
- *Error (data load failed):* "Couldn't load upcoming predictions. Retry." with Retry.
- *Per-card states:* `Scheduled (predicts in ~Xh)`, `Running…`, `Predicted`, `Failed`, `Missed window`.

**Match Detail (`/matches/[id]`)**
- *Empty/Not predicted yet:* "Not predicted yet — scheduled for ~{time}." Action: Predict now.
- *Loading:* skeleton for prediction, evidence, result panels independently.
- *Populated (pre-match):* prediction + evidence; result panel shows "Kickoff {countdown}."
- *Populated (post-match):* prediction vs result + grade + evidence.
- *Error (prediction failed):* failure reason + Retry + (admin) View raw output.
- *Awaiting result:* "Match finished — fetching result." + Grade now.
- *Result needs review:* candidate results + Confirm.
- *Success (after manual run):* toast "Prediction updated (v{n})" / "Match graded."
- *Disabled:* Predict now disabled when already running ("A run is in progress for this match"); Grade now disabled pre-kickoff ("Available after full-time").

**Results / History (`/history`)**
- *Empty:* "No graded matches yet. The first results will appear after matches finish."
- *Empty (filtered to zero):* "No matches match these filters. Clear filters."
- *Loading / Populated / Error:* standard.

**Accuracy Dashboard (`/dashboard`)**
- *Empty (n < threshold, e.g. <5 graded):* "Not enough graded matches yet for reliable trends — {n} so far. Metrics unlock at {threshold}." Show raw counts meanwhile.
- *Loading:* chart skeletons.
- *Populated:* metric tiles (outcome %, exact-score %, goals MAE, scorer recall, confidence Brier) + trend chart + calibration summary (↑/↓ vs first half, current bias text).
- *Error:* "Couldn't compute metrics. Retry."
- *Disabled:* metric toggles disabled until enough data.

**Admin · Runs (`/admin/runs`)**
- *Empty:* "No runs yet. Trigger one or wait for the scheduler ({next run time})."
- *Loading / Populated:* run list with per-fixture results, durations, spend.
- *Error:* per-run failure rows with reason + Retry.

**Admin · Config (`/admin/config`)**
- *Populated:* form (prediction window hours, cadence, per-run fixture cap, spend cap, use-odds toggle).
- *Error (validation):* inline per-field (see table).
- *Success:* "Config saved. Applies to the next scheduler run." (note: doesn't retroactively change existing predictions).
- *Disabled:* Save disabled until a field changes / while invalid.

## Accessibility notes

- **Focus order — Upcoming:** on load, focus the header accuracy strip's first metric, then fixture list in kickoff order. After triggering a run, focus moves to the affected fixture card's status.
- **Focus order — Match Detail:** on load, focus the match title (teams + kickoff), then prediction summary, then result (if present), then evidence. On run completion, focus the updated panel.
- **Focus — dialogs:** confirm dialogs trap focus, focus the safe/Cancel button by default for destructive actions (re-run, mark void); on close, return focus to the triggering control.
- **Screen-reader announcements (live regions):**
  - Status transitions: "Prediction running for {match}", "Prediction ready for {match}", "Prediction failed for {match}: {reason}", "Match graded: predicted {x}, actual {y}."
  - Toasts ("Config saved", "Marked void") announced via `aria-live="polite"`; failures via `assertive`.
- **Keyboard traps to avoid:** charts must have a keyboard-accessible data table fallback; status chips that are also links must be reachable and operable by keyboard; no drag-only interactions.
- **Status not by color alone:** prediction status and grade (hit/miss) must carry text/icon, not just red/green (color-blind safety) — flagged for the UI agent.

## Analytics events

> Even single-user, these power the dashboard and debugging. (Internal telemetry, not user tracking.)

| Step | Event name | Payload | Success signal |
|------|-----------|---------|----------------|
| Scheduler selects fixtures | `run_started` | `{run_id, type: predict\|grade, fixture_count}` | Run begins |
| Per-fixture data fetch | `data_fetched` | `{fixture_id, source_count, data_quality: ok\|low}` | ≥1 source returned |
| Prediction produced | `prediction_created` | `{fixture_id, model_id, prompt_version, calibration_version, confidence, retries}` | Schema-valid prediction stored |
| Prediction failed | `prediction_failed` | `{fixture_id, reason, retries}` | Visible failure recorded (not silent) |
| Result fetched | `result_fetched` | `{fixture_id, decided_by, needs_review: bool}` | Result stored |
| Match graded | `match_graded` | `{fixture_id, exact_hit, outcome_correct, goals_abs_err}` | Grade stored |
| Calibration recomputed | `calibration_updated` | `{version, n_graded}` | New profile version |
| Manual run triggered | `manual_run_triggered` | `{fixture_id, type}` | Run starts |
| Match detail viewed | `match_viewed` | `{fixture_id, has_result}` | — (engagement) |
| Void toggled | `match_voided` | `{fixture_id, voided: bool}` | Excluded/restored in metrics |

## Friction points and UX risks

- **"Is it broken or just not due?" ambiguity (highest risk):** the single most important UX job is distinguishing `Scheduled` vs `Running` vs `Failed` vs `Missed window`. Solved via explicit, distinct status chips + next-run time everywhere.
- **Empty-app coldness early in the tournament:** first matchdays have few graded matches, so the dashboard is sparse. Mitigation: show counts/“unlocks at N” messaging and make Upcoming + evidence compelling from match one.
- **Trust in numbers:** if dashboard aggregates don't reconcile with per-match grades, the whole product loses credibility. Mitigation: every aggregate links to the underlying graded matches; voids clearly excluded.
- **Hidden spend on re-runs:** manual re-run silently costs API/search money. Mitigation: confirm dialog states the cost implication.
- **Calibration legibility:** "is it improving?" must be a glanceable arrow + plain-language bias summary, not just a Brier number most users can't interpret.
- **Result correctness:** a wrong auto-fetched result poisons metrics. Mitigation: `Result needs review` state for source conflicts + manual confirm + editable ground truth.
- **Versioning confusion:** multiple prediction versions per fixture could confuse. Mitigation: show latest by default, with a clearly-labeled version history.

## Handoff to UI and dev

**Routes/screens:** `/`, `/matches/[fixtureId]`, `/history`, `/dashboard`, `/admin/runs`, `/admin/config` (ratify with architecture agent).

**Components/modules likely needed:**
- `FixtureCard` with `StatusChip` (5 states), `PredictionSummary` (score + scorers + confidence), `HeaderMetricsStrip`.
- `MatchDetail` composed of `PredictionPanel`, `ResultPanel`, `GradeBadge` (hit/miss, text+icon), `EvidencePanel` (sources, versions, data-quality badge).
- `MetricTile`, `TrendChart` (+ accessible data-table fallback), `CalibrationSummary`.
- `RunsTable`, `FailureRow` with Retry, `ConfigForm`.
- `ConfirmDialog` (focus-managed), `Toast` (live-region wired).

**Validation rules (with messages):**

| Field | Rule | Message |
|-------|------|---------|
| Prediction window (h) | 1–72 integer | "Enter a window between 1 and 72 hours." |
| Cadence | from allowed set (e.g. hourly/6h/daily) | "Choose a valid cadence." |
| Per-run fixture cap | ≥1 integer | "Cap must be at least 1." |
| Spend cap | ≥0 number | "Spend cap can't be negative." |
| Mark void | requires confirm | "Void this match? It will be excluded from accuracy metrics. You can restore it later." |
| Re-run prediction | requires confirm | "Re-running creates a new prediction version and incurs API/search cost. Continue?" |

**Must-exist states in code:** every screen's empty/loading/error states above; the 5 fixture statuses; `Awaiting result`, `Result needs review`, `Low data quality`, `Missed window`, `void`.

**Micro-interactions:** status chip transitions (Scheduled→Running→Predicted/Failed), skeletons on independent panels, optimistic "Running…" on manual trigger, toasts for run completion/config save, countdown to kickoff on pre-match detail.

**Next:** UI agent (`/ui-design-systems-agent`) to turn these screens/states into a component + token plan; then architecture (`/tech-lead-architecture-agent`) to ratify routes, entities, and the run/scheduler model.

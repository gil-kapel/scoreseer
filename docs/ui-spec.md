# UI Spec: ScoreSeer

> Builds on [docs/ux-flows.md](ux-flows.md) and [docs/prd.md](prd.md). Defines components, tokens, and states — not animation polish.

## Goal

Give a single analyst a calm, data-dense "control room" for World Cup 2026 predictions: glance at what's predicted next and whether the system is improving, then drill into any prediction's evidence and grade — all auditable, all trustworthy.

## Clarifying answers captured

- **Visual direction:** Data-dense analyst dark — terminal/Bloomberg-like. Compact tables, tabular/monospaced numerals, charts foregrounded. Reference feel: financial analytics dashboards (dense rows, restrained chrome, numbers as the hero).
- **Theme:** Dark default, light toggle available (`@custom-variant dark`).
- **Stack:** Next.js (App Router) + shadcn/ui + Tailwind v4 + cva + lucide-react + Recharts for viz. Talks to the Python backend over a typed API client.
- **Deliverable:** component + token plan and a Stitch-ready prompt.
- **No Dribbble upload needed:** direction is explicit (analyst-dark, numbers-first); inspiration captured below.

## Component tree (hierarchy)

```
AppShell
├─ SidebarNav            (Upcoming, History, Dashboard, Admin▸Runs/Config; collapses on mobile)
├─ TopBar
│  ├─ HeaderMetricsStrip (outcome %, exact-score %, goals MAE, calibration ↑/↓)  ← global, persistent
│  ├─ NextRunIndicator   ("next run in ~Xh")
│  └─ ThemeToggle
└─ <RouteContent>
   ├─ / (Upcoming)
   │  ├─ SectionHeader ("Upcoming · {date range}")
   │  └─ FixtureList → FixtureCard[]
   │     ├─ MatchTeams (flags/abbr, kickoff countdown)
   │     ├─ StatusChip (5 states)
   │     ├─ PredictionSummary (scoreline, top scorers+likelihood, ConfidenceMeter)
   │     └─ DataQualityBadge?  (low-data flag)
   ├─ /matches/[fixtureId] (Match Detail)
   │  ├─ MatchHeader (teams, stage/group, kickoff, status, VersionSelector)
   │  ├─ PredictionPanel (ScoreLine, ScorerList[ScorerRow w/ likelihood bar], ConfidenceMeter, ExplanationBlock)
   │  ├─ ResultPanel (actual ScoreLine, actual scorers, decided-by row) | states: pre-match / awaiting / review / final
   │  ├─ GradeBadgeRow (exact-hit, outcome, goals-error, scorer P/R — text+icon, not color-only)
   │  ├─ EvidencePanel (SourceList w/ links, signal chips: form/lineups/injuries/H2H/odds, version footer)
   │  └─ AdminActionBar (Predict now / Grade now / Re-run / Mark void) — owner only
   ├─ /history
   │  ├─ FilterBar (stage, outcome hit/miss, date)
   │  └─ ResultsTable (sortable, virtualized) → row → Match Detail
   ├─ /dashboard
   │  ├─ MetricTileGrid (MetricTile[] with sparkline)
   │  ├─ AccuracyTrendChart (cumulative outcome% / exact% over matchdays)
   │  ├─ CalibrationPanel (reliability curve + first-half vs second-half Brier + BiasSummary text)
   │  └─ ScorerQualityPanel (precision/recall, Brier trend)
   └─ /admin
      ├─ /runs → RunsTable → RunDetailDrawer (per-fixture outcomes, FailureRow + Retry, spend)
      └─ /config → ConfigForm (window, cadence, caps, odds toggle)

Shared: ConfirmDialog, Toast/Sonner, EmptyState, ErrorState, SkeletonRow, StatPill, CountdownTimer
```

## Token system

Tailwind v4 `@theme`, OKLCH. Brand → semantic → component. Dark is the base; light overrides under `@custom-variant dark`.

```css
@theme {
  /* Surfaces (dark base) */
  --color-bg:            oklch(0.17 0.01 250);   /* app background */
  --color-surface:       oklch(0.21 0.012 250);  /* cards/panels */
  --color-surface-2:     oklch(0.25 0.014 250);  /* nested rows, table header */
  --color-border:        oklch(0.30 0.012 250);
  --color-fg:            oklch(0.96 0.01 250);    /* primary text */
  --color-fg-muted:      oklch(0.72 0.012 250);  /* secondary text */

  /* Brand / accent */
  --color-primary:       oklch(0.70 0.16 230);   /* analyst blue — links, active nav, primary CTA */
  --color-primary-fg:    oklch(0.16 0.01 250);

  /* Status / semantic (paired with icons + text, never color-alone) */
  --color-success:       oklch(0.74 0.17 150);   /* hit / on-track */
  --color-danger:        oklch(0.66 0.20 25);    /* miss / failed */
  --color-warning:       oklch(0.80 0.15 85);    /* low-data / needs review */
  --color-info:          oklch(0.72 0.13 230);   /* running */
  --color-neutral:       oklch(0.60 0.01 250);   /* scheduled / void */

  /* Confidence scale (sequential, for meters/heat) */
  --color-conf-low:      oklch(0.66 0.20 25);
  --color-conf-mid:      oklch(0.80 0.15 85);
  --color-conf-high:     oklch(0.74 0.17 150);

  /* Typography */
  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;  /* scores, metrics, likelihoods */
  --text-caption: 0.75rem;   /* 12 */
  --text-body:    0.875rem;  /* 14 — dense default */
  --text-h3:      1.125rem;  /* 18 */
  --text-h2:      1.5rem;    /* 24 */
  --text-score:   2.25rem;   /* 36 — hero scoreline, mono, tabular-nums */

  /* Spacing — 4px grid, tight rhythm for density */
  --spacing-page: 1.5rem;
  --radius-default: 0.5rem;
  --radius-sm: 0.375rem;
  --radius-pill: 9999px;
}
```

Conventions: all numerals use `font-mono` + `tabular-nums` so columns align. Density: row height ~36–40px; `--text-body` is 14px default.

## shadcn/ui components used

`card`, `badge`, `button`, `table`, `tabs`, `dialog` (ConfirmDialog), `sonner` (toasts), `tooltip`, `dropdown-menu` (version/filters), `select`, `input`, `switch` (odds toggle, theme), `skeleton`, `separator`, `sheet`/`drawer` (RunDetail, mobile nav), `progress` (confidence/likelihood bars), `alert` (error/low-data), `popover`, `scroll-area`.

## Custom components (cva variants)

- **StatusChip** — `variant: scheduled | running | predicted | failed | missed`. Each pairs an icon (lucide: `Clock`, `Loader2`(spin), `CheckCircle2`, `XCircle`, `AlertTriangle`) + label + color. Never color-only.
- **GradeBadge** — `variant: hit | miss | partial`, `metric: exact | outcome | scorer`. Shows icon + short label + value (e.g. "✓ Exact 2–1", "✕ Outcome").
- **ConfidenceMeter** — `level: low | mid | high` (derived from value); segmented bar + numeric %.
- **LikelihoodBar** — inline mini `progress` per ScorerRow with mono % label.
- **MetricTile** — `trend: up | down | flat`; big mono value + label + sparkline + delta-vs-first-half.
- **DataQualityBadge** — `quality: ok | low`; warning style when low with tooltip listing missing signals.
- **EmptyState / ErrorState** — `context`-driven copy (per UX doc's exact strings) + optional action.

cva keeps variant→token mapping centralized so dark/light and color-blind-safe pairings stay consistent.

## States by component

| Component | Default | Loading | Empty | Error | Success | Disabled |
|-----------|---------|---------|-------|-------|---------|----------|
| FixtureCard | Prediction + StatusChip | SkeletonRow | n/a (list-level) | per-card "Failed" + Retry | "Predicted" chip | — |
| FixtureList | Cards by kickoff | 5 skeleton cards | "No matches in window yet… next: {fixture} {date}" | "Couldn't load. Retry" | — | — |
| PredictionPanel | Score+scorers+conf+why | skeleton | "Not predicted yet — ~{time}" + Predict now | "Prediction failed: {reason}" + Retry/View raw | toast "Prediction updated (v{n})" | Predict now disabled while running (tooltip) |
| ResultPanel | actual vs predicted | skeleton | "Kickoff {countdown}" (pre-match) | "Result needs review" + candidates+Confirm | "Match graded" | Grade now disabled pre-FT (tooltip) |
| GradeBadgeRow | hit/miss badges | skeleton | hidden pre-result | — | — | — |
| AccuracyTrendChart | line chart | chart skeleton | "Not enough graded matches — {n}. Unlocks at {N}" | "Couldn't compute. Retry" | — | toggles disabled until N |
| CalibrationPanel | reliability curve + bias text | skeleton | "Calibration available after {N} grades" | retry | — | — |
| RunsTable | runs + outcomes | skeleton rows | "No runs yet — next {time}" | failure rows + Retry | toast on retry success | Retry disabled while running |
| ConfigForm | populated form | skeleton | — | inline per-field validation | "Config saved. Applies next run." | Save disabled until changed/valid |

## Responsive behavior

- **Desktop (≥1024px):** persistent SidebarNav + multi-column. Match Detail = two columns (Prediction | Result) with Evidence full-width below. Dashboard = tile grid (3–4 wide) + charts.
- **Tablet (640–1023px):** sidebar collapses to icon rail; Match Detail columns stack; dashboard tiles 2-wide.
- **Mobile (<640px):** nav becomes a `sheet` (hamburger); HeaderMetricsStrip condenses to a horizontally-scrollable StatPill row; tables (History/Runs) switch to stacked cards; charts get an accessible data-table toggle. ScoreLine stays large/legible.
- **Overflow:** team names truncate to abbreviations with full name in tooltip; long explanations clamp with "show more".

## Accessibility notes

- **Status & grades never color-only** — every StatusChip/GradeBadge carries icon + text (WCAG 1.4.1).
- **Contrast:** verify all semantic colors on `--color-surface` meet 4.5:1 (large mono scores 3:1). OKLCH lightness chosen with margin; light theme re-verified.
- **Keyboard:** full Tab path; ConfirmDialog traps focus, Cancel focused by default for destructive actions (re-run, void), focus returns to trigger on close. Charts have a keyboard-reachable data-table fallback.
- **Focus order** per [ux-flows.md](ux-flows.md): Upcoming → metrics strip → fixtures; Match Detail → title → prediction → result → evidence.
- **Live regions:** Sonner wired to `aria-live` — `polite` for "Config saved/Prediction ready", `assertive` for failures. Status transitions announced ("Prediction running for {match}").
- **Icon-only buttons** (theme toggle, retry) get `aria-label`. Visible focus rings via `--color-primary`.

## Visual inspiration notes

Borrowed from financial-analytics dashboards: dense aligned rows, mono tabular numerals, muted chrome so data/charts pop, sparklines inside metric tiles, restrained accent (single analyst-blue primary). Product-specific: football scoreline as hero, team flags/abbreviations, confidence/likelihood meters, and the calibration reliability curve (the "are we improving?" signal). Avoided: heavy sportsbook gradients, team-color theming (would fight the neutral analyst surface), and decorative imagery.

## Stitch-ready prompt

```
Design a dark-mode, data-dense analytics web app called "ScoreSeer" — a single-user "accuracy lab" that predicts FIFA World Cup 2026 match results and grades itself over time. Visual feel: a calm financial/Bloomberg-style control room. Muted dark surfaces (near-black blue-gray), one analyst-blue accent, monospaced tabular numerals for all scores/metrics, compact aligned rows, charts foregrounded. Inter for text, JetBrains Mono for numbers.

Build these screens:
1. Upcoming (home): left sidebar nav; a persistent top metrics strip (outcome accuracy %, exact-score %, goals MAE, calibration trend ↑/↓) and a "next run in ~Xh" indicator; a list of fixture cards. Each card: team abbreviations + flags, kickoff countdown, a STATUS CHIP that must show distinct states with BOTH icon and text — Scheduled (clock), Running (spinner), Predicted (check), Failed (x), Missed window (alert) — a predicted scoreline, top 2 likely scorers each with a small likelihood % bar, and a confidence meter. Some cards show a yellow "Low data" badge.
2. Match Detail: header with teams/stage/kickoff and a version selector; a Prediction panel (large mono scoreline, scorer list with per-player likelihood bars, confidence meter, short explanation) beside a Result panel (actual score + scorers once finished); a row of grade badges (Exact ✓/✕, Outcome ✓/✕, total-goals error, scorer precision/recall) using icon+text not color alone; an Evidence panel listing sources with links, signal chips (form, lineups, injuries, head-to-head, odds), and a small footer with model/prompt/calibration version. Owner action bar: Predict now, Grade now, Re-run, Mark void.
3. Accuracy Dashboard: a grid of metric tiles each with a big mono value and sparkline; a cumulative accuracy trend line chart over matchdays; a calibration panel with a reliability curve and a plain-language bias summary ("over-predicts favourite blowouts by ~0.4 goals") plus first-half vs second-half Brier comparison.
4. Admin Runs: a dense table of scheduler runs with per-fixture outcomes, durations, spend, and failed rows with a Retry button.

Requirements: WCAG AA contrast; status and grade meaning conveyed by icon+text+color together (color-blind safe, no red/green-only); skeleton loading states; empty states with helpful copy ("No matches in the prediction window yet"); a light theme variant. Dense but uncluttered — numbers are the hero.
```

## Build notes for dev

- **From shadcn:** install the components listed above into `components/ui/` (owned copies). Product components (`FixtureCard`, `StatusChip`, `MetricTile`, …) live in `components/` and compose primitives — never edit `components/ui/` directly.
- **Variants:** model every status/grade/confidence as a cva variant so the color-blind-safe icon+color pairing lives in one place; expose a typed `status`/`variant` prop driven by API enums.
- **Numbers:** global utility class for `font-mono tabular-nums`; format scores/percentages centrally.
- **Charts:** Recharts (Accuracy trend = `LineChart`; Calibration = `ScatterChart`/`LineChart` reliability curve; sparklines = tiny `LineChart`). Always render an accessible `<table>` fallback toggle.
- **Theme:** dark base tokens in `@theme`; `@custom-variant dark` + a `data-theme`/class toggle persisted to localStorage; verify both themes' contrast.
- **Animation:** `@starting-style` for panel/dialog enter; `Loader2` spin for Running; keep motion subtle (analyst calm). Respect `prefers-reduced-motion`.
- **State source:** all status/grade/quality enums come from the backend API — UI is presentation-only; no LLM calls from the client (per NFR: reads render <1s from stored data).
- **Data contracts:** UI consumes the entities from [prd.md](prd.md) handoff (Fixture, Prediction, Result, Grade, DataSnapshot, CalibrationProfile) — to be ratified by the architecture agent next.

**Next:** architecture (`/tech-lead-architecture-agent`) to ratify routes/entities/API + the scheduler model, then implementation slices (`/dev-composer-agent`).

# M2 — Frontend / Interface Engineer

**Name:** _TBD_ · **Buddy:** M1

## Mission
Make the farmer's journey (Observe → Experiment → Decide) clear, exact to Figma, accessible and honest about sources and uncertainty.

## Owns
`frontend/` (screens, components, design tokens, charts, map, Data Journey view, Playwright visual checks).

## Inputs → Outputs
- **In:** Figma frames, generated types `frontend/src/types/contracts.ts`, API endpoints (M1), uncertainty wording (M5).
- **Out:** the working UI, screenshot comparisons, a list of UI assumptions in `docs/decisions.md`.

## Tasks

### H0–H6
- [ ] Get the Figma link and frame IDs; extract design tokens (colour, type, spacing) into `frontend/src/styles/tokens.css`.
- [ ] App shell with three steps (Observe / Experiment / Decide) plus the Data Journey view, running on DEMO fixtures with a visible `DEMO` badge.
- [ ] Shared components: `SourceLabel` (short label + details drawer), `StatusPill` (text + icon, not colour alone), `RangeBar` (p10/p50/p90).

### H6–H24 Observe & Experiment
- [ ] **Observe:** map (MapLibre) with field boundary, native data footprints and a static fallback image; environmental timeline; farmer-input form (soil, irrigation allocation, equipment, crop availability, market/use).
- [ ] **Experiment:** three aligned rotation rows (2–3 seasons, longer horizon disclosed); priorities panel separate from hard constraints; infeasibility reasons shown inline.
- [ ] **Replay player:** shared weather timeline driving all three rows; play/pause/step; pause at the turning point; edit a supported input → rerun → the chart updates only once the new result arrives (show a loading/stale state in between).

### H24–H36 Decide & Data Journey
- [ ] **Decide:** three strategy cards (benefits, disadvantages, ranges labelled "central 80% simulation range", missing info), trade-off view, "choose and record reason", decision-card export button.
- [ ] **Data Journey:** 9 stage cards, each with a one-sentence explanation, status, one chart, "What does this mean?" and source details.
- [ ] States: empty, loading, missing data, failed run, unavailable scenario (disabled with a reason).
- [ ] Keyboard navigation for the whole main flow; visible focus; legends readable.
- [ ] Playwright screenshots vs Figma frames at matching viewports; differences either fixed or recorded.

### H36–H48
- [ ] Bug fixes only; support the demo rehearsal; capture screenshots for the pitch.

## Outcomes (definition of done for M2)
| Outcome | Accepted when |
|---|---|
| Figma fidelity | Every supplied frame has a screenshot comparison; deviations are recorded with a reason |
| Source disclosure | Every chart, map layer, metric and export shows a source label with expandable details |
| Honest results | No chart shows stale results after an edit; unsupported edits are disabled with a reason; ranges use the agreed wording |
| Data Journey | All 9 stages render from real payloads (or clearly marked DEMO), with ≤ 1 main chart each |
| Accessibility | Main flow fully keyboard-operable; status never conveyed by colour alone |
| Robust states | Empty/loading/missing/failed/unavailable states exist for every data view |
| Type safety | No hand-written contract types; strict TS, lint clean |

## Cut order (M2 area)
Trade-off scatter → simple table; animated replay → stepper; map tiles → static image.

# Farm Time Machine — Team Plan & Task Split (5 members, 48h)

## Context
Source docs: [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) and Farm_Time_Machine_Team_Report.pdf. Repo is empty apart from these. Goal: ship one convincing demo — preset farm → history → confirm inputs → current practice + 2 alternatives → shared historical-weather replay → trade-offs with ranges + evidence → decision card — while obeying the 4 mandatory rules (standard libs, cite every source, follow Figma exactly, visible Data Journey).

The guide defines 5 responsibility areas (Data, Engine, Validation, Interface, Research/Demo). Mapped to 5 people as Tech Lead / Frontend / Backend-Data / Simulation Engine / ML-Validation, with Research/Demo split across Lead + Engine.

## Recommended stack (confirm at H0 — guide leaves it open)
- **Backend/science:** Python 3.12, FastAPI, pandas/numpy/xarray, `pyfao56` (USDA FAO-56 implementation → satisfies Rule 1), `earthengine-api` (MODIS/GPM/SMAP), pytest, pydantic for contracts.
- **Frontend:** React + TypeScript + Vite, MapLibre GL (with static fallback image), ECharts or Recharts, Playwright for Figma screenshot compare.
- **Storage: PostgreSQL + static files (hybrid)**
  - **PostgreSQL 16 + PostGIS** (Docker Compose; SQLAlchemy 2 + Alembic migrations; psycopg 3). Holds everything queryable: Site (boundary as PostGIS geometry), Source register, Observation (raw value, processed value, quality/imputation flags, processing-run ID — one row per site/source/variable/day), ProcessingRun, CropSoilProfile, Strategy, SimulationRun, Result (quantiles, metric/unit, source IDs, limitations), Validation, decision records. Native data footprints stored as PostGIS polygons for the map.
  - Large daily time series: plain indexed table partitioned by source (or TimescaleDB hypertable if volume justifies it — decide after H12 volume check).
  - **Static files** where they fit better: immutable raw snapshots as downloaded (`data/raw/<source>/<retrieval_date>/…`, checksummed, path + hash recorded in Source/Observation rows); MODIS/GEE rasters and image thumbnails (GeoTIFF/PNG/Cloud-Optimized GeoTIFF); bulk ensemble traces (Parquet, `results/<run_id>/traces.parquet`, referenced from Result rows); exported decision cards (PDF/JSON); static map fallback tiles.
  - Rule: DB rows never overwrite raw values; processed outputs are new versioned rows tied to a ProcessingRun.
  - Demo reliability: seed script + `pg_dump` snapshot of the demo DB and a tarball of the static files, so the whole demo restores offline.
  - FastAPI serves results from the DB; reruns for supported edits write new SimulationRun/Result rows.
- **Repo:** monorepo `backend/`, `frontend/`, `data/`, `docs/`, `contracts/` (JSON Schema shared by both sides). CI: lint + pytest + typecheck.

## Roles and ownership

### M1 — Technical Lead (architecture, integration, delivery)
- H0–H2: run kickoff; lock decision log (site, crops, stack, Figma link) in `docs/decisions.md`; scaffold monorepo + CI + Docker Compose (Postgres/PostGIS, API, frontend); write `contracts/` schemas for the 9 entities (Site, Source, Observation, ProcessingRun, CropSoilProfile, Strategy, SimulationRun, Result, Validation) and co-design the DB schema with M3 (M1 owns API-facing tables: Strategy, SimulationRun, Result, decisions).
- Build fixture JSON (labeled DEMO) so FE and Engine can start before real data exists.
- Own the API layer (FastAPI routes: `/sites`, `/sources`, `/journey`, `/strategies`, `/runs`, `/results/{id}`, `/decision-card`), run-ID/provenance plumbing, and result cache.
- Integration owner: merges, code review, enforces "no cosmetic chart updates on stale results" and "unsupported combo → disabled, never nearest".
- Decision-card export (PDF/JSON with sources, run IDs, model version, limitations) backend side.
- H36+: feature freeze gate, demo script, recorded demo, offline/backup rehearsal, submission. Co-owns pitch with M5.

### M2 — Frontend / Interface Engineer
- H0–H6: get Figma frames; extract tokens/components; set up layout shell (Observe / Experiment / Decide) against fixtures.
- Observe: farm map + evidence layers with native footprint + source labels; environmental timeline; farmer-input confirmation form (soil, irrigation allocation, equipment, crop availability).
- Experiment: 3 aligned rotation rows (editable 2–3 seasons), priorities vs hard-constraints panel, infeasibility reasons, replay player (shared weather, pause at turning point, edit → rerun).
- Decide: 3 strategy cards, p10/p50/p90 ranges labelled "central 80% simulation range", trade-off view, decision-card screen + "record your reason".
- Data Journey view: 9 stage cards (Collect…Compare), one chart each, status, "What does this mean?", expandable source details.
- Every chart gets source label + details drawer (Rule 2). Keyboard nav, colour-independent status, empty/loading/missing/failed/unavailable states. Playwright screenshot comparisons vs Figma.

### M3 — Backend / Data Engineer
- H0–H2: verify access to NASA POWER daily API, GEE (MOD13Q1, GPM IMERG V07, SMAP L4), soil source (OpenLandMap-soildb or local); report blockers.
- Own Postgres schema for data tables (Site, Source, Observation, ProcessingRun, CropSoilProfile) + Alembic migrations, indexes, PostGIS footprints; volume check at H12 (TimescaleDB only if needed); seed + `pg_dump` demo snapshot with M1.
- Source adapters → immutable raw files on disk (checksummed) + Source rows with full metadata (product/version, units, resolution, coverage, retrieval date, DOI, license, QA flags).
- QA/cleaning pipeline producing versioned processed data: decode QA flags/scale factors, duplicate policy, unit conversion, variable-specific gap rules (rain gaps flagged, never zero-filled), observed/estimated/missing flags preserved.
- Alignment to daily site series with native-footprint metadata; one declared rainfall source per run.
- Emit per-stage stats (expected/received/missing/flagged counts, raw-vs-clean diffs, gap lists) as JSON for Data Journey stages Collect→Align.
- H12 target: real POWER weather cached for site; Collect/Check/Clean views fed with real data. Later: GPM/SMAP only if early access check passes.

### M4 — Simulation Engine Engineer (+ crop research)
- H0–H4: with M5/local contacts, pick 4–6 crops; build crop/soil catalog with cited Kc stages, root depth, durations, p-factor, uncertainty (no invented params — missing = blocked/flagged).
- Daily water balance on `pyfao56` (or thin wrapper): ET0 (Penman-Monteith from POWER, Hargreaves fallback with correct Ra units), runoff, infiltration, AET under stress, drainage, bounded storage, carryover across crops/seasons, warm-up.
- Two modes: irrigation-needed under rule; stress under fixed allocation (no silent unlimited water).
- Rotation logic: sequence/dates/termination, hard-constraint feasibility with human-readable reasons, cover/residue, low-cover exposure days, diversity index.
- Replay engine: identical weather across 3 strategies, per-day traces for the player; supported-edit set (irrigation limit, planting window) recomputable.
- H24 target: 3 strategies run end-to-end on real weather. Then ensemble: season-aligned block bootstrap + consecutive-year replay, paired parameter draws, seeded; 50 → 500 paths after stability check.
- Unit tests: mass balance, bounds, units, dates, determinism, paired forcing.

### M5 — ML / Validation & Uncertainty Engineer (+ pitch)
- Phenology/season detection from quality-filtered MODIS NDVI/EVI (smoothing e.g. Savitzky-Golay via scipy, threshold/derivative season start/end); fallback to local calendar, clearly disclosed. Feeds "Extract" stage + possible low-cover windows.
- Calendar evaluation vs farmer records/local calendars (timing differences reported).
- Weather-ensemble coverage evaluation: chronological/rolling splits, held-out sample counts, empirical coverage + interval width; untouched final test period. Optional conformal only with separate calibration data.
- Sensitivity analysis on soil AWC / management inputs → "does ranking change?" (powers the memorable interaction).
- Owns Validate stage JSON + honest failure reporting; reviews all UI wording on uncertainty.
- Research/demo: references register, limitations text, first-user test, pitch deck + script with M1.
- Note: no yield ML — cut first per guide; the "ML" here is phenology + uncertainty/validation.

## Timeline (checkpoints from guide)
| Checkpoint | Done means | Key owners |
|---|---|---|
| H0–H2 | Site, crops, 3 strategies, stack, contracts agreed; data access verified; DEMO fixtures in repo | M1 lead, all |
| H12 | Real weather cached; 1 strategy runs; Collect/Check/Clean views live; UI shell on fixtures | M3, M4, M2 |
| H24 | 3 strategies + replay end-to-end on real outputs; phenology v1; comparison UI consumes real results | M4, M2, M5, M1 |
| H36 | Feature freeze; ranges, evidence, validation, Data Journey complete; Figma comparison done | All, M1 gate |
| H44 | Demo recorded; docs + decision-card export checked; backup tested | M1, M5 |
| H44–48 | Fixes + submission buffer | All |

## Handoffs / dependencies
- M1 contracts + fixtures (H2) unblock M2 and M4.
- M3 processed weather (H12) → M4 engine; M3 MODIS → M5 phenology.
- M4 results + traces → M1 API → M2 UI; M4 ensemble → M5 validation.
- Pair-ups for no single-person dependency: M3↔M5 (data/phenology), M4↔M1 (engine/API), M2↔M1 (UI integration). Stagger rest shifts so each pair has one awake.

## Cut order (protect core)
Cut: yield ML, arbitrary locations, 2nd region, future climate, 3D/fancy charts, 500 paths (keep 50–100), GPM/SMAP. Protect: 3 strategies, shared replay, truthful ranges, basic Data Journey, constraints, source disclosure.

## Verification
- `pytest` suite (mass balance, units, bounds, dates, paired forcing, reproducibility by seed) green in CI.
- Alembic `upgrade head` on an empty DB + seed script reproduces the demo; restore from `pg_dump` + static tarball on a clean machine.
- End-to-end demo path run from the local DB + cached files with network off (verify, don't assume).
- Playwright screenshot diff vs Figma frames at matching viewports.
- Walk the Definition-of-Done checklist (guide §11) at H36 and H44.

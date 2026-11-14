# AGENTS.md — How AI agents work in this repo

Read this file fully before you change anything. It applies to every coding agent (Claude Code, Codex, Copilot, Cursor, etc.) working in this repository.

## 1. What this project is

**Farm Time Machine** — NASA Space Apps 2026, challenge "Field Shift: Adapting Farms with NASA Data".
A decision-support tool that lets a farmer rehearse crop rotations against historical weather. It compares water use and soil protection, and shows the uncertainty before the farmer plants.

The demo story we must ship:
select a preset farm → inspect its history → confirm inputs → compare current practice and two alternatives → replay the same weather → inspect trade-offs and evidence → save a decision card.

Authoritative documents (read in this order):

1. [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md): the rules, scientific boundaries and definition of done. **It wins over everything else, including this file.**
2. [TEAM_PLAN.md](TEAM_PLAN.md): roles, stack, timeline.
3. [docs/team/](docs/team/): one brief per member, with tasks and expected outcomes.
4. [docs/decisions.md](docs/decisions.md): resolved decisions. Anything not recorded there is still **open**.

## 2. Who you are working for

Every agent session acts on behalf of one team member. Find out which one (ask if unclear), read that member's brief in `docs/team/`, and stay inside that member's area:

| Member | Role | Primary paths |
|---|---|---|
| M1 | Technical Lead | `backend/src/ftm/api/`, `backend/src/ftm/contracts/`, `contracts/`, `docker-compose.yml`, `.github/`, `docs/decisions.md` |
| M2 | Frontend | `frontend/` |
| M3 | Backend / Data | `backend/src/ftm/data/`, `backend/src/ftm/db/`, `backend/alembic/`, `data/` |
| M4 | Simulation Engine | `backend/src/ftm/engine/`, `backend/src/ftm/engine/catalog/` |
| M5 | ML / Validation | `backend/src/ftm/validation/` |

Changes outside your member's paths are allowed only when they are small and necessary (for example a one-line import fix). Call them out in the PR description so the owner reviews them. **Never change a shared contract (`backend/src/ftm/contracts/`, `contracts/`, DB models or migrations) without M1 approval.** Propose the change in the PR instead.

## 3. The four mandatory rules (from the guide; non-negotiable)

1. **Use standard, established libraries.** Don't reinvent dates, units, parsing, numerics, geospatial handling, charts or FAO-56 (use `pyfao56`). Add a dependency only if it's maintained and needed. Pin an exact version and note the license in the PR. Write custom code only for project-specific logic, and test it.
2. **Always identify the data sources used.** Every map layer, chart, metric, recommendation and export carries the IDs of the sources it actually used, plus its processing-run ID. Keep observations, model or reanalysis data, farmer inputs, literature parameters and simulated outputs distinguishable. Label demo data visibly as `DEMO`. Never list a source that was only considered, and never imply NASA endorsement.
3. **Follow the supplied Figma exactly.** Once frames are supplied, they are the visual source of truth. Don't redesign or approximate. Don't invent a Figma URL or claim pixel fidelity without a screenshot comparison. For an unspecified state, extend existing patterns and record the assumption in `docs/decisions.md`.
4. **Keep the pipeline visible and simple.** Every stage (Collect, Check, Clean, Handle gaps, Align, Extract, Simulate, Validate, Compare) must emit the small status/summary payload the Data Journey view needs. Don't build workflow editors, and don't show raw logs as the main UI.

## 4. Scientific and data honesty (hard stops)

An agent must **never**:

- Fabricate data, crop parameters, accuracy figures, coverage numbers, yields, profits, soil-carbon gains or validation results. If a value is unknown, leave it `null` and flag it as missing. A missing crop parameter blocks the claim; it is never filled with a guess.
- Treat missing rainfall as zero, or interpolate rainfall by default.
- Overwrite raw values. Raw files are immutable, and processed data is a new versioned output tied to a `ProcessingRun`.
- Silently substitute the "nearest" precomputed scenario for an unsupported edit. Unsupported means disabled or explicitly computed.
- Update a chart cosmetically while the underlying result is stale.
- Silently give unlimited irrigation in fixed-allocation (water-stress) mode.
- Call p10–p90 a "prediction interval" or "confidence". It is a "central 80% simulation range" unless coverage has actually been evaluated.
- Present GWETROOT or SMAP L4 as direct field measurements, low NDVI as proof of bare soil, or historical resampling as a climate forecast.
- Sum two rainfall sources in one run.
- Turn a candidate (site, crop, stack choice) into a fact. Open decisions stay open until recorded in `docs/decisions.md`.

When the correct scientific choice is unclear, stop and ask the member. Don't guess.

## 5. Architecture and conventions

```
backend/            Python 3.12, uv, FastAPI, SQLAlchemy 2, Alembic, pydantic v2
  src/ftm/
    contracts/      pydantic models = SINGLE SOURCE OF TRUTH for API/data shapes (M1)
    db/             SQLAlchemy ORM models + session (M3, schema changes approved by M1)
    api/            FastAPI app and routes (M1)
    data/           source adapters, raw cache, QA/clean/gaps/align pipeline (M3)
    engine/         water balance, rotation, replay, ensemble, crop catalog (M4)
    validation/     phenology, coverage, sensitivity (M5)
    provenance.py   run IDs, checksums
  alembic/          migrations (never edit an applied migration; add a new one)
  scripts/          export_contracts.py, seed_demo.py
  tests/
frontend/           React + TypeScript + Vite (M2); types generated from contracts/
contracts/schemas/  JSON Schema GENERATED from backend contracts. Do not hand-edit.
data/raw/           immutable downloads (gitignored, checksummed, referenced from DB)
data/processed/     versioned processed outputs (gitignored)
data/fixtures/      small committed DEMO fixtures (must carry "demo": true)
results/            large run artefacts, e.g. Parquet traces (gitignored)
docs/               decisions, data-source register, model notes, team briefs
```

Storage rule: **PostgreSQL + PostGIS** holds everything queryable. Large or immutable blobs (raw downloads, rasters, Parquet traces, exported cards) live on disk, and the DB rows that use them reference the path and SHA-256.

### Contract workflow

1. Change the pydantic model in `backend/src/ftm/contracts/`.
2. Run `make contracts`. It regenerates `contracts/schemas/*.json` and `frontend/src/types/contracts.ts`.
3. If storage changes, update the ORM model and add an Alembic migration (`make migration m="..."`).
4. Commit everything together. CI fails if the generated files are stale.

### Code style

- Python: type hints everywhere, `ruff` for lint and format, `mypy`-clean public functions, units in names or docstrings (`rain_mm`, `et0_mm_day`, `ra_mj_m2_day`). Use timezone-aware datetimes and keep the original timestamps.
- TypeScript: strict mode, no `any` on contract data, ESLint clean.
- Small, focused modules. Comments explain *why* or cite a source (FAO-56 equation number, DOI). They don't narrate code.
- A scientific method needs a docstring citation and a test.

## 6. Commands

```bash
make up           # start Postgres/PostGIS (docker compose)
make install      # backend (uv sync) + frontend (pnpm install)
make migrate      # alembic upgrade head
make seed         # load DEMO fixtures into the DB
make api          # run FastAPI on :8000 (docs at /docs)
make web          # run the frontend dev server on :5173
make test         # backend pytest + frontend typecheck/lint
make lint         # ruff + eslint
make contracts    # regenerate JSON Schema + TS types from pydantic contracts
```

Before saying a task is done, run `make lint test`. Report failures exactly as printed, and never claim a test passed if you didn't run it.

## 7. Required tests for scientific code

Engine and pipeline changes must keep or extend tests for: units, mass balance (`Δstorage = infiltrated rain + irrigation − AET − drainage`), physical bounds, crop-calendar date logic, carry-over between seasons, identical forcing across strategies, and determinism for a fixed seed. Use `hypothesis` for property tests where it helps.

## 8. Git and PRs

- Branch from `main`: `m<N>/<short-topic>`, e.g. `m3/power-adapter`. Never push directly to `main`.
- Commit or push only when your member asks you to.
- Use small PRs and the PR template. List the sources touched, the contract changes and any scientific assumptions.
- Never commit secrets (`.env`, Earthdata or GEE credentials), raw downloads or large artefacts.

## 9. When to stop and ask

- Before an open decision is resolved (site, crops, parameters, Figma, stack changes).
- When a data source is inaccessible, its license is unclear, or its quality fails a check. Report it; don't work around it silently.
- Before any destructive action (dropping tables, deleting data under `data/`, force-pushing).
- When the guide and a member's request conflict. Quote the guide section and ask.

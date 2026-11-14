# Data: how it flows and how to use it

Owner: M3 (+ M5 for seasons and validation). For teammates and their coding agents.

## Load a site (one command)

```bash
docker compose up -d db                       # project Postgres/PostGIS (see .env for the port)
cd backend && uv sync && uv run alembic upgrade head
uv run python scripts/load_site.py --site-id ks-field-2 --name "Kansas field 2 (irrigated pivot)" \
  --lat 38.01517 --lon -100.92496 --timezone America/Chicago \
  --boundary ../docs/site-search/ks-field-2.geojson --area-ha 45.8 \
  --status "primary site (D3); local confirmation pending"
# add --skip-modis without an Earth Engine sign-in (see docs/data-sources.md, access check)
uv run python scripts/evaluate_phenology.py --site-id ks-field-2   # needs NASS_API_KEY; stores the validation
```

`load_site.py` runs, in order: `load_power.py` (weather), `load_soil.py` (SSURGO in the US, SoilGrids elsewhere,
per decision D8) and `load_modis.py` (satellite greenness + pixel outline). Then it prints the Data Journey.
Re-running creates new processing runs and keeps the old ones.

## How data flows

```
download ──► data/raw/<source>/<date>/  (unchanged bytes + SHA-256, never overwritten)
         ──► Source row (provider, version, units, coverage, licence, checksum, limitations)
         ──► pipeline: check → clean → handle gaps → align  (weather)   |   QA flags + scale (MODIS)
         ──► ProcessingRun row (every step, its parameters and counts; Data Journey payloads)
         ──► Observation rows (raw value kept + processed value + quality flag, per run)
```

Rules the pipeline enforces (and tests): raw values are never changed; missing is NULL/NaN and never 0; rain
gaps are never filled; short gaps in other weather variables (≤ 2 days) are estimated and flagged; impossible
values are rejected, not clipped; cloud/snow satellite values are kept and flagged, never used.

## What to call

| Need | Call | Returns |
|---|---|---|
| Daily weather for the engine (M4) | `ftm.data.forcing.get_daily_forcing(site_id, start, end, weather_source_id, session=...)` | Wide frame: one row per day, `<VAR>` + `<VAR>__flag`; `attrs`: `source_ids`, `processing_run_id`, `units` |
| Soil water capacity (M4) | `soil_profile` row for the site (SoilProfile contract) | `available_water_capacity_mm_per_m` with low–high in `uncertainty`; root depth null (crop parameter) |
| Satellite greenness | `ftm.data.vegetation.get_vi_composites(site_id, session=...)` | One row per 16-day composite: NDVI, EVI, QA, `qa_pass`, acquisition date |
| Detected seasons (M4, M1) | `ftm.validation.site_seasons.get_site_seasons(site_id, session)` | Seasons + low-cover windows with the tuned parameters |
| Data Journey (M1 route, M2 screen) | `ftm.data.journey.build_journey(site_id, session)` | Nine `JourneyStage` payloads in order; Align carries map layers (field, satellite pixel, weather grid point) |
| Validation results | `validation` table / `ftm.validation.report.validate_stage(...)` | Stored `Validation` records with failures and sample counts |

Units are in the column names or the Source record (`T2M_MAX` °C, `PRECTOTCORR` mm/day, `ALLSKY_SFC_SW_DWN`
MJ/m²/day, `RH2M` %, `WS2M` m/s at 2 m, NDVI unitless).

## Where to read more
- Sources, licences and access checks: `docs/data-sources.md`
- Site choice and evidence: `docs/site-search/`, `docs/decisions.md` (D3, D8)
- Limits to show in the UI: `docs/limitations.md`
- Walkthroughs with charts: `notebooks/01_weather_eda.ipynb`, `notebooks/02_season_detection.ipynb`
- Validation plan and results: `docs/validation-plan.md`, `docs/validation-results.md`

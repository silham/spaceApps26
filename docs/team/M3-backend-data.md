# M3 — Backend / Data Engineer

**Name:** _TBD_ · **Buddy:** M5

## Mission
Get real NASA and soil data in, keep it traceable from download to chart, and never hide a gap.

## Owns
`backend/src/ftm/data/` (adapters, raw cache, pipeline), `backend/src/ftm/db/` + `backend/alembic/` (schema changes approved by M1), `data/`, `docs/data-sources.md` (source register).

## Inputs → Outputs
- **In:** chosen site and date range (kickoff), the variables M4 and M5 need.
- **Out:** a processed daily weather series (M4), quality-filtered MODIS VI series (M5), soil properties with uncertainty (M4), Data Journey stats for Collect→Align (M1/M2).

## Tasks

### H0–H2
- [ ] Verify access to: NASA POWER daily API, Google Earth Engine (MOD13Q1; optionally GPM IMERG V07, SMAP L4), soil source (OpenLandMap-soildb or local). Record the access route, license and blockers in `docs/data-sources.md`.
- [ ] Agree the variable list with M4 (e.g. T2M_MAX, T2M_MIN, PRECTOTCORR, ALLSKY_SFC_SW_DWN, RH2M, WS2M; confirm the names in the POWER docs).
- [ ] First Alembic migration reviewed with M1.

### H2–H12
- [ ] NASA POWER adapter → raw JSON saved under `data/raw/power/<retrieval_date>/` with SHA-256 + a `Source` row (product/version, units, resolution, coverage, retrieval date, URL, license, limitations).
- [ ] Load raw values into `observation` (raw value kept forever).
- [ ] Pipeline v1: decode fill values/QA, unit conversions, duplicate policy, variable-specific gap rules (rain gaps flagged, never zero-filled; declared max gap for short continuous-variable gaps). Writes processed values with flags under a new `ProcessingRun`.
- [ ] Data Journey payloads for Collect, Check and Clean (expected/received/missing/duplicate/flagged/rejected counts; raw vs cleaned sample).
- [ ] **H12: real POWER weather for the site in the DB and visible in the UI.**

### H12–H24
- [ ] MODIS MOD13Q1 extraction via GEE for the field: quality-filtered NDVI/EVI with scale factor applied, pixel footprint stored as PostGIS geometry, raw export cached.
- [ ] Soil properties (AWC/texture/depth) with provider attribution and stated uncertainty.
- [ ] Handle-gaps and Align payloads: original gaps, estimated values, unresolved gaps, method; native resolutions, aggregation rule, timezone.
- [ ] Processed-weather accessor for the engine: `get_daily_forcing(site_id, start, end, rain_source) -> DataFrame` with flags and source IDs.

### H24–H36
- [ ] Optional: GPM/SMAP only if the H2 access check passed and the schedule allows. One rainfall source per run, with an overlap/bias note.
- [ ] Seed script and `pg_dump` demo snapshot with M1; static-file tarball.
- [ ] Data section of the README / docs.

## Outcomes (definition of done for M3)
| Outcome | Accepted when |
|---|---|
| Source register | Every used dataset has provider, product/version, variable, units, native resolution, coverage, retrieval date, URL/DOI, license, QA notes, limitations |
| Immutable raw | Raw downloads on disk with checksums; DB raw values never modified |
| Versioned processing | Every processed value links to a ProcessingRun with steps, parameters and affected counts |
| Gap honesty | Missing rainfall never zero-filled; estimated values flagged; long gaps left unresolved or explicitly handled |
| Engine-ready forcing | M4 can call one function to get daily forcing with flags and source IDs |
| Data Journey | Collect, Check, Clean, Handle-gaps, Align payloads available via API |
| Reproducible | Fresh DB + `make migrate seed` + cached raw files reproduce the processed data |

## Cut order (M3 area)
GPM/SMAP → drop; soil maps → documented local default with disclosure; MODIS → disclosed local-calendar fallback (coordinate with M5).

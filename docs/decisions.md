# Decision log

Owner: M1. Anything not recorded here as **Resolved** is still open (DEVELOPMENT_GUIDE.md §13).
Record each decision with date, owner, rationale and the assumptions it affects. Don't silently turn candidates into facts.

| # | Decision | Status | Date | Owner | Rationale / affected assumptions |
|---|---|---|---|---|---|
| D1 | Storage: PostgreSQL 16 + PostGIS for queryable data; static files for raw snapshots, rasters, Parquet traces, exports | Resolved | 2026-11-14 | M1 | Expected data volume; spatial queries for footprints; raw immutability via checksummed files |
| D2 | Stack: Python 3.12 / FastAPI / SQLAlchemy / Alembic; React + TS + Vite | Proposed, confirm at kickoff | 2026-11-14 | M1 | Scientific library support (pyfao56, scipy, pandas) |
| D3 | Primary site: **Kansas `ks-field-2`**, a 46 ha irrigated centre-pivot field in Finney County (38.01517, −100.92496), 6.9 km from the original Garden City point. Sri Lanka small-plot blocks (sl-block-1…3) kept as a later extension | Resolved | 2026-11-14 | M3 (team request) | Original points were not fields (Kansas inside Garden City; Sri Lanka tree cover). Field found by `scripts/find_candidate_fields.py` (`docs/site-search/`): one cropped field every year 2018–2024 (USDA CDL), MODIS pixel fully inside, soil SSURGO silt loam (AWC 214 mm/m). CDL history corn ↔ winter wheat; MODIS shows the wheat peak (May–June) in both wheat years (2019, 2021), followed by a second green-up in Aug–Sep: likely a double crop or regrowth after wheat harvest, **to confirm locally** (not COVID: 2019 predates it; May 2019 was Kansas's wettest May on record, but western Kansas wheat conditions were near-optimal per K-State). Upland and irrigated, so no paddy model is needed (guide §3). **Remote evidence only: planting dates, irrigation allocation and equipment still need local/farmer confirmation.** Sri Lanka extension will use Sentinel-2 (10 m) because its plots are far smaller than a MODIS pixel. |
| D4 | Crops (4–6) and parameters | Open | | M4/M5 | |
| D5 | Current practice + 2 alternative rotations | Open | | M4 | |
| D6 | Supported edits (e.g. irrigation limit, planting window) | Open | | M1/M4 | |
| D7 | Rainfall source per run (POWER vs GPM) | Open | | M3 | One source per run; never summed |
| D8 | Soil information source: **USDA SSURGO (Soil Data Access) if the site is in the US; ISRIC SoilGrids 2.0 otherwise** | Resolved | 2026-11-14 | M3 | Both access routes verified. SSURGO gives AWC with documented low/high per horizon (feeds sensitivity, validation plan §4); SoilGrids is the global fallback, AWC derived from field capacity − wilting point means with no AWC interval (sensitivity uses the declared ±20% assumption). Root depth stays a crop parameter (M4). OpenLandMap-soildb not used: no verified access route. |
| D9 | Figma link and frame IDs | Open | | M2 | |
| D10 | Validation references | Open | | M5 | |
| D11 | Second region | Open (cut-first) | | M1 | |

## UI assumptions for states not specified in Figma
<!-- M2: list each assumption here -->

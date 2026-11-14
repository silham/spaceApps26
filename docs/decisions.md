# Decision log

Owner: M1. Anything not recorded here as **Resolved** is still open (DEVELOPMENT_GUIDE.md §13).
Record each decision with date, owner, rationale and the assumptions it affects. Don't silently turn candidates into facts.

| # | Decision | Status | Date | Owner | Rationale / affected assumptions |
|---|---|---|---|---|---|
| D1 | Storage: PostgreSQL 16 + PostGIS for queryable data; static files for raw snapshots, rasters, Parquet traces, exports | Resolved | 2026-11-14 | M1 | Expected data volume; spatial queries for footprints; raw immutability via checksummed files |
| D2 | Stack: Python 3.12 / FastAPI / SQLAlchemy / Alembic; React + TS + Vite | Proposed, confirm at kickoff | 2026-11-14 | M1 | Scientific library support (pyfao56, scipy, pandas) |
| D3 | Primary site (candidates: western Kansas, Sri Lanka) | Open | | M1/M5 | Upland pilot preferred unless paddy ponding/percolation can be supported |
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

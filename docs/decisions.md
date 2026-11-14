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
| D8 | Soil information source | Open | | M3 | |
| D9 | Figma link and frame IDs: file `CWGXpY5vu06StB7waehMt5` ("spaceapps26"), frame `3:2` "Farm Time Machine / Primary dashboard" (1440×2223), local components `3:5`–`3:13`, `3:172` | Proposed, M1 to confirm | 2026-11-14 | M2 | Only this one frame is supplied. Its footer reads "Design concept — provided Figma frames supersede this mockup", so confirm it is the final visual source. No Figma variables are defined; tokens in `frontend/src/styles/tokens.css` are the frame's raw values |
| D10 | Validation references | Open | | M5 | |
| D11 | Second region | Open (cut-first) | | M1 | |

## UI assumptions for states not specified in Figma
<!-- M2: list each assumption here -->

Recorded 2026-11-14 while implementing Figma frame `3:2` (see D9). Each item is an assumption, not a resolved decision.

**Content**

- **Overview content is the frame's illustrative content.** Strategy names, crops, metric values, sampling metadata, run ID `R-014`, field area and constraint values come from `frontend/src/demo/figmaDemo.ts`, shown under the frame's own DEMO labels. They are not API data or model output. The site list and pipeline statuses do come from the API when it serves them. Wire the rest as the contract covers it (soil-cover results, paired deltas, run metadata, crop names).
- **Source footer text needs M1/M3 review.** The frame says "Demo run rainfall: NASA POWER only · Vegetation context: MODIS". No POWER or MODIS data backs the illustrative numbers, so under guide rule 2 this line should change or go once real sources are registered.
- **"Saved just now" is replaced by the API connection status** ("API connected" / "Connecting…" / "API unreachable") in the same slot, because nothing is saved yet.
- **The user name "Shakil" in the sidebar is static** frame content; there is no sign-in.

**Unspecified states and interactions**

- **Views without a frame** (Rotation planner, Data Journey, Evidence & validation) reuse the dashboard's card, control and status-chip patterns and show API data only.
- **Outdated state.** The frame shows results outdated because the irrigation limit changed. Any further constraint edit is appended to the banner. "Run comparison" calls `POST /runs`; while that returns 501 an inline alert is shown under the banner and the results stay marked outdated. Choosing a strategy and exporting stay disabled while outdated.
- **Constraint dropdowns offer only their current value** until the supported-edit set is decided (D6).
- **Disabled with a reason (tooltip):** Vegetation and Data footprints map layers, "Irrigation needed" mode, "Replay a dry year", "Edit farm details".
- **Map is the static illustrative image** with the frame's overlay (cut order: map tiles → static image). MapLibre is not used yet.
- **Replay.** The scrubber gets a visible thumb (the frame draws none) so it can be dragged. Timeline columns are equal width, so the playhead moves piecewise through an illustrative calendar: the 18 Jun boundary is taken from the frame, the 1 Oct boundary is a placeholder. Speeds offered: 1×, 2×, 4×.
- **"Show scenario ranges"** toggles the "central 80% simulation range" lines on the strategy cards.
- **Sidebar is sticky** at viewport height; in the frame it runs the full page height.
- **Layout is fluid above 1180 px** and matches the frame at 1440 px.
- **Inter (the frame's typeface) is bundled as a font file** in `frontend/src/assets/fonts/` (latin subset from `@fontsource-variable/inter` 5.3.0, SIL OFL 1.1, licence alongside), so the app renders the same offline. It is a copied file, not a package dependency.

**Fidelity check**

- Checked once on 2026-11-14 at a 1440 px viewport against the frame's screenshot: section positions and sizes are within about 5 px (page height 2212 px vs 2223 px in the frame, because the frame rounds control heights up to 36 px). This was a manual comparison; the Playwright visual check is not automated yet.

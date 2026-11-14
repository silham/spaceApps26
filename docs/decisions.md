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
| D9 | Figma link and frame IDs: file `CWGXpY5vu06StB7waehMt5` ("spaceapps26"), page `0:1`. Implemented frame: `25:49` "Farm Time Machine / Dashboard — Redesign v2" (1440×2918) with component set `24:49` and logo `12:55`. The earlier frame `3:2` (1440×2223) and its component set `3:3` are superseded and kept in the file only for history | Proposed, M1 to confirm | 2026-11-14 | M2 | The footer on both frames reads "Design concept — provided Figma frames supersede this mockup", so confirm v2 is the final visual source. No Figma variables are defined; tokens in `frontend/src/styles/tokens.css` are the frame's raw values |
| D10 | Validation references | Open | | M5 | |
| D11 | Second region | Open (cut-first) | | M1 | |

## UI assumptions for states not specified in Figma
<!-- M2: list each assumption here -->

Recorded 2026-11-14 while implementing Figma frame `25:49` (see D9). Each item is an assumption, not a resolved decision.

**Content**

- **Overview content is the frame's illustrative content.** Strategy names, crops, metric values, sampling metadata, run ID `R-014`, field area and constraint values come from `frontend/src/demo/figmaDemo.ts`, shown under the frame's own DEMO labels. They are not API data or model output. The site list and pipeline statuses do come from the API when it serves them. Wire the rest as the contract covers it (soil-cover results, paired deltas, run metadata, crop names).
- **Source footer text needs M1/M3 review.** The frame says "Demo run rainfall: NASA POWER only · Vegetation context: MODIS". No POWER or MODIS data backs the illustrative numbers, so under guide rule 2 this line should change or go once real sources are registered.
- **The "Saved just now" badge in the top bar is replaced by the API connection status** ("API connected" / "Connecting…" / "API unreachable") in the same slot, because nothing is saved yet.
- **The user name "Shakil" / "Farm planner" in the sidebar is static** frame content; there is no sign-in.

**Unspecified states and interactions**

- **Views without a frame** (Rotation planner, Data Journey, Evidence & validation) reuse the dashboard's card, control and status-chip patterns and show API data only.
- **Outdated state.** The frame shows results outdated because the irrigation limit changed. Any further constraint edit is appended to the banner. "Run comparison" calls `POST /runs`; while that returns 501 an inline alert is shown under the banner and the results stay marked outdated. Choosing a strategy and exporting stay disabled while outdated.
- **Constraint dropdowns offer only their current value** until the supported-edit set is decided (D6).
- **Disabled with a reason (tooltip):** Vegetation and Data footprints map layers, "Irrigation needed" mode, "Replay a dry year", "Edit farm details".
- **Map is the static illustrative image** with the frame's overlay (cut order: map tiles → static image). MapLibre is not used yet.
- **Replay.** The frame's scrubber is a static image; it is a draggable range input here. Timeline columns are equal width, so the playhead moves piecewise through an illustrative calendar; both column boundaries (21 Apr, 4 Aug) are placeholders chosen so that 18 Jun lands where the frame draws its playhead. Speeds offered: 1×, 2×, 4×. The pause state is drawn as two bars (the frame shows only play).
- **"Show scenario ranges"** toggles the "central 80% simulation range" lines on the strategy cards.
- **Sidebar is sticky** at viewport height; in the frame it runs the full page height.
- **Heat-exposure row** (frame node `28:458`) was not fetched from Figma because the MCP call limit was reached; it is rebuilt from the frame screenshot and layer outline, using the info icon in place of the frame's thermometer icon. Re-fetch and replace when the limit resets.
- **Range bars** on the strategy cards use fixed display axes (water stress 0–35 days, soil cover 170–270 days) so the three strategies line up; the frame's bar positions imply the same axes. The axes are illustrative until real results exist.
- **Mode toggle** (Fixed allocation / Irrigation needed) is the frame's segmented control; "Irrigation needed" is disabled with a reason because the run has no such results.
- **Layout is fluid above 1240 px** and matches the frame at 1440 px.
- **Inter (the frame's typeface) is bundled as a font file** in `frontend/src/assets/fonts/` (latin subset from `@fontsource-variable/inter` 5.3.0, SIL OFL 1.1, licence alongside), so the app renders the same offline. It is a copied file, not a package dependency.

**Fidelity check**

- Checked on 2026-11-14 at a 1440 px viewport against the v2 frame's screenshot: section positions and sizes are within a few pixels (page height 2916 px vs 2918 px). This was a manual comparison; the Playwright visual check is not automated yet.

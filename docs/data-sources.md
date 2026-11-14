# Source register

Owner: M3. List only sources **actually used** (AGENTS.md rule 2). Candidates go under "Considered". Each entry must match a `Source` row in the DB.

## Used

| ID | Provider | Product / version | Variables (units) | Native res. (space / time) | Coverage | Retrieved | URL / DOI | License / attribution | QA & limitations |
|---|---|---|---|---|---|---|---|---|---|
| `power_e085e3004e7553c0` (Kansas candidate) · `power_217ab3c27c9a4a6a` (Sri Lanka candidate) | NASA Langley Research Center POWER Project | POWER Daily API v2.10.3, community AG (point) | T2M_MAX, T2M_MIN, T2MDEW (°C), PRECTOTCORR (mm/day), ALLSKY_SFC_SW_DWN (MJ/m²/day), RH2M (%), WS2M (m/s) | MERRA-2 met ~0.5°×0.625°; solar ~1°×1° / daily (local solar time) | 1981-01-01 – 2025-12-31 (**solar from 1984**) | 2026-11-14 | https://power.larc.nasa.gov/docs/services/api/temporal/daily/ | NASA open data; acknowledgment: "These data were obtained from the NASA Langley Research Center (LaRC) POWER Project funded through the NASA Earth Science/Applied Science Program." | Reanalysis/satellite-derived, not field data; fill −999 decoded as missing; no solar 1981–1983; Sri Lanka 1995–1996 rainfall flagged suspect (explorer screening rule) |
| `ssurgo_551d4bd7def7b956` (Kansas candidate) | USDA Natural Resources Conservation Service | SSURGO via Soil Data Access; survey area KS055, version 2026-08-27 | awc_l / awc_r / awc_h (cm/cm), texture, sand/silt/clay (%) | Soil map unit polygon (survey scale) / static | Map unit 1152313 "Las clay loam, deep, occasionally flooded" | 2026-11-14 | https://sdmdataaccess.sc.egov.usda.gov/ | US public domain; cite Soil Survey Staff, NRCS, USDA, SSURGO Database | Map units generalise several components; representative estimates, not field measurements; low/high are documented ranges, not statistical intervals |
| `soilgrids_367c683772270dd0` (Sri Lanka candidate) | ISRIC – World Soil Information | SoilGrids 2.0 REST point query | wv0033, wv1500 (% vol), clay/sand/silt (%) | 250 m / static | Point 8.31, 80.40 | 2026-11-14 | https://rest.isric.org/soilgrids/v2.0/docs · doi:10.5194/soil-7-217-2021 | CC BY 4.0; cite Poggio et al. (2021) SOIL 7, 217–240 | Model predictions; very wide 5–95% ranges at this point (e.g. clay ~1–87%); AWC derived from means, no AWC interval available |

## Considered (not yet used)

- MODIS MOD13Q1 v061: https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1
- GPM IMERG V07: https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- SMAP L4 (SPL4SMGP v008): https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008
- OpenLandMap-soildb: https://doi.org/10.5194/essd-18-989-2026

## Access check (H0–H2)

| Source | Access route | Works? | Blocker / notes |
|---|---|---|---|
| NASA POWER | HTTPS API | Yes | Slow/IPv6-less networks: works over IPv4 |
| MOD13Q1 | Earth Engine | | |
| GPM IMERG | Earth Engine | | |
| SMAP L4 | Earth Engine | | |
| Soil (US) | USDA Soil Data Access REST (SQL) | Yes | US only |
| Soil (global) | ISRIC SoilGrids 2.0 REST | Yes | Intermittent TLS timeouts; adapter retries; ~45 s per query |
| OpenLandMap-soildb | — | Not checked | No verified access route yet; stays under Considered |

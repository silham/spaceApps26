# Source register

Owner: M3. List only sources **actually used** (AGENTS.md rule 2). Candidates go under "Considered". Each entry must match a `Source` row in the DB.

## Used

| ID | Provider | Product / version | Variables (units) | Native res. (space / time) | Coverage | Retrieved | URL / DOI | License / attribution | QA & limitations |
|---|---|---|---|---|---|---|---|---|---|
| `power_e085e3004e7553c0` (Kansas candidate) · `power_217ab3c27c9a4a6a` (Sri Lanka candidate) | NASA Langley Research Center POWER Project | POWER Daily API v2.10.3, community AG (point) | T2M_MAX, T2M_MIN, T2MDEW (°C), PRECTOTCORR (mm/day), ALLSKY_SFC_SW_DWN (MJ/m²/day), RH2M (%), WS2M (m/s) | MERRA-2 met ~0.5°×0.625°; solar ~1°×1° / daily (local solar time) | 1981-01-01 – 2025-12-31 (**solar from 1984**) | 2026-11-14 | https://power.larc.nasa.gov/docs/services/api/temporal/daily/ | NASA open data; acknowledgment: "These data were obtained from the NASA Langley Research Center (LaRC) POWER Project funded through the NASA Earth Science/Applied Science Program." | Reanalysis/satellite-derived, not field data; fill −999 decoded as missing; no solar 1981–1983; Sri Lanka 1995–1996 rainfall flagged suspect (explorer screening rule) |
| `ssurgo_551d4bd7def7b956` (Kansas candidate) | USDA Natural Resources Conservation Service | SSURGO via Soil Data Access; survey area KS055, version 2026-08-27 | awc_l / awc_r / awc_h (cm/cm), texture, sand/silt/clay (%) | Soil map unit polygon (survey scale) / static | Map unit 1152313 "Las clay loam, deep, occasionally flooded" | 2026-11-14 | https://sdmdataaccess.sc.egov.usda.gov/ | US public domain; cite Soil Survey Staff, NRCS, USDA, SSURGO Database | Map units generalise several components; representative estimates, not field measurements; low/high are documented ranges, not statistical intervals |
| `soilgrids_367c683772270dd0` (Sri Lanka candidate) | ISRIC – World Soil Information | SoilGrids 2.0 REST point query | wv0033, wv1500 (% vol), clay/sand/silt (%) | 250 m / static | Point 8.31, 80.40 | 2026-11-14 | https://rest.isric.org/soilgrids/v2.0/docs · doi:10.5194/soil-7-217-2021 | CC BY 4.0; cite Poggio et al. (2021) SOIL 7, 217–240 | Model predictions; very wide 5–95% ranges at this point (e.g. clay ~1–87%); AWC derived from means, no AWC interval available |
| `modis_16db0348c7059516` (Kansas candidate) · `modis_d972848745cf795a` (Sri Lanka candidate) | NASA LP DAAC (MODIS Terra), via Google Earth Engine | MOD13Q1 v061, 16-day L3 250 m | NDVI, EVI (unitless, scale 0.0001), SummaryQA, DetailedQA, DayOfYear | 250 m nominal (231.66 m sinusoidal) / 16-day composite | 2000-02-18 – 2025-12-19 | 2026-11-14 | doi:10.5067/MODIS/MOD13Q1.061 | NASA data, no reuse restrictions; cite Didan (2021) | Fill −3000 → missing; snow/ice and cloudy kept and flagged; qa_pass = good/marginal. One pixel ≈ a small field (mixed pixels). **Candidate points are not crop fields** (WorldCover 2021: Kansas 93 % built-up, Sri Lanka 76 % tree cover); Sri Lanka 37–54 % usable May–Nov (cloud). |

## Considered (not yet used)

- GPM IMERG V07: https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- SMAP L4 (SPL4SMGP v008): https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008
- OpenLandMap-soildb: https://doi.org/10.5194/essd-18-989-2026
- ESA WorldCover 10 m v200 (2021), via Earth Engine `ESA/WorldCover/v200`: used for the land-cover check and the Sri Lanka field search (`docs/site-search/`), not part of app data. CC BY 4.0.
- USDA NASS Cropland Data Layer 2018–2024, via Earth Engine `USDA/NASS/CDL`: used for the land-cover check and the field search (`docs/site-search/`), not part of app data. Public domain.
- USDA NAIP aerial imagery (2023), via Earth Engine `USDA/NAIP/DOQQ`: photos in `docs/site-search/` only. Public domain.
- Copernicus Sentinel-2 L2A (Jan–Apr 2024), via Earth Engine `COPERNICUS/S2_SR_HARMONIZED`: photos in `docs/site-search/` only. Contains modified Copernicus Sentinel data.

## Access check (H0–H2)

| Source | Access route | Works? | Blocker / notes |
|---|---|---|---|
| NASA POWER | HTTPS API | Yes | Slow/IPv6-less networks: works over IPv4 |
| MOD13Q1 | Earth Engine | Yes | Tested 2026-11-14 on project farm-time-machine: MODIS/061/MOD13Q1 returns NDVI, EVI, DetailedQA, SummaryQA, DayOfYear + reflectance/angle bands. `earthengine authenticate` is blocked by Google (asks for Drive scope); use `ee.Authenticate(scopes=[earthengine, cloud-platform])` or gcloud application-default login with those scopes. |
| GPM IMERG | Earth Engine | | |
| SMAP L4 | Earth Engine | | |
| Soil (US) | USDA Soil Data Access REST (SQL) | Yes | US only |
| Soil (global) | ISRIC SoilGrids 2.0 REST | Yes | Intermittent TLS timeouts; adapter retries; ~45 s per query |
| OpenLandMap-soildb | — | Not checked | No verified access route yet; stays under Considered |

# References

Owner: M5. Every method, parameter and dataset cited anywhere in the code, UI or pitch. Grouped by use.
"Used" means it feeds the app or a reported result. Search-only sources are marked.

## Challenge
- NASA Space Apps 2026, *Field Shift: Adapting Farms with NASA Data*: https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/

## Data used by the app
- **NASA POWER** daily point API, community AG, v2.10.3 (MERRA-2 meteorology; CERES/SRB solar): https://power.larc.nasa.gov/docs/services/api/temporal/daily/. Acknowledgment: "These data were obtained from the NASA Langley Research Center (LaRC) POWER Project funded through the NASA Earth Science/Applied Science Program."
- **MODIS MOD13Q1 v061**: Didan, K. (2021). *MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061*. NASA EOSDIS Land Processes DAAC. doi:10.5067/MODIS/MOD13Q1.061
- **USDA NRCS SSURGO** via Soil Data Access: Soil Survey Staff, Natural Resources Conservation Service, USDA. *Soil Survey Geographic (SSURGO) Database*. https://sdmdataaccess.sc.egov.usda.gov/
- **ISRIC SoilGrids 2.0** (global soil fallback): Poggio, L. et al. (2021). SoilGrids 2.0: producing soil information for the globe with quantified spatial uncertainty. *SOIL* 7, 217–240. doi:10.5194/soil-7-217-2021 (CC BY 4.0)

## Validation reference data
- **USDA NASS Crop Progress** (Kansas, weekly % planted) via the Quick Stats API: https://quickstats.nass.usda.gov/api. Reference for season-start evaluation (validation plan v1.2).
- **USDA NASS Cropland Data Layer** 2006–2024 (crop per year at the field; also the field search): https://www.nass.usda.gov/Research_and_Science/Cropland/

## Field search only (not app data)
- ESA WorldCover 10 m 2021 v200: Zanaga, D. et al. (2022). doi:10.5281/zenodo.7254221 (CC BY 4.0)
- USDA NAIP aerial imagery (2023), public domain: https://naip-usdaonline.hub.arcgis.com/
- Copernicus Sentinel-2 L2A (Jan–Apr 2024); contains modified Copernicus Sentinel data.
- Google Earth Engine (access to MODIS, CDL, WorldCover, NAIP, Sentinel-2): Gorelick, N. et al. (2017). Google Earth Engine: planetary-scale geospatial analysis for everyone. *Remote Sensing of Environment* 202, 18–27. doi:10.1016/j.rse.2017.06.031

## Methods
- **FAO-56**: Allen, R.G., Pereira, L.S., Raes, D. & Smith, M. (1998). *Crop evapotranspiration*. FAO Irrigation and Drainage Paper 56. https://www.fao.org/4/x0490e/x0490e00.htm (Hargreaves units: https://www.fao.org/4/x0490e/x0490e07.htm)
- **ASCE standardized reference ET** (explainer ET₀ in the notebooks, via `pyfao56.refet.ascedaily`): ASCE-EWRI (2005). *The ASCE Standardized Reference Evapotranspiration Equation*. American Society of Civil Engineers. pyfao56: https://github.com/kthorp/pyfao56
- **Season start/end (amplitude threshold)**: Jönsson, P. & Eklundh, L. (2004). TIMESAT: a program for analyzing time-series of satellite sensor data. *Computers & Geosciences* 30, 833–845. doi:10.1016/j.cageo.2004.05.006
- **Smoothing**: Savitzky–Golay filter via SciPy `scipy.signal.savgol_filter`. SciPy: Virtanen, P. et al. (2020). SciPy 1.0. *Nature Methods* 17, 261–272. doi:10.1038/s41592-019-0686-2
- **Binomial interval for coverage**: Clopper, C.J. & Pearson, E.S. (1934). The use of confidence or fiducial limits illustrated in the case of the binomial. *Biometrika* 26, 404–413. Via `scipy.stats.binomtest(...).proportion_ci(method="exact")`.
- **Conformal prediction under non-exchangeability** (optional, not used yet): https://jmlr.org/papers/v25/23-1553.html
- **Plausibility bounds** in the cleaning step: WMO Weather & Climate Extremes Archive, https://wmo.asu.edu/ ; top-of-atmosphere radiation limit: FAO-56 Annex 2.

## Context sources (cited in findings, not data)
- K-State Agronomy eUpdate, *Overview of the 2019 Kansas wheat growing season*: https://eupdate.agronomy.ksu.edu/article/overview-of-the-2019-kansas-wheat-growing-season-348
- AP (2019-06-21), *Heavy May rains delaying Kansas wheat harvest*: https://m.washingtontimes.com/news/2019/jun/21/heavy-may-rains-delaying-kansas-wheat-harvest/
- K-State SWREC (Garden City), double-crop forage sorghum after wheat: https://journals.newprairiepress.org/kaesrr/article/7029/galley/6965/download/

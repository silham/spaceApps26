# Limitations (data, satellite and validation)

Owner: M5 (with M3). Plain-language limits for the UI's "What does this mean?" panels, the decision card and the
pitch. Each line is something the app must say or must never claim. The simulation engine's own limits
belong to M4 (`docs/model.md`).

## The site
- `ks-field-2` was chosen from **remote evidence** (crop maps, satellite, aerial photos). Planting dates,
  irrigation allocation and equipment are **not yet confirmed locally**. Say "pending local confirmation"
  wherever farmer context is shown.
- The field outline is **approximate** (derived from a 30 m crop map).
- Crop history comes from the USDA Cropland Data Layer, a **classified map**: accurate for major crops, but not
  a farm record.

## Weather (NASA POWER)
- Values are **gridded reanalysis and satellite estimates**, not measurements at the field. One weather cell is
  roughly 50 km across, so the numbers describe the area, not the farm.
- **No solar radiation before 1984**, so ET₀ and water balance start in 1984. Earlier years are rain-only.
- Daily values are summed in **local solar time**, which can differ from the clock day by up to about an hour.
- Missing values are shown as missing and **never filled with zero**. Missing rain is never interpolated.
- Sri Lanka candidate only: 1995–1996 rainfall looks implausible (flagged, unconfirmed).

## Soil
- SSURGO values are **representative estimates for a mapped soil unit**, not field measurements. The low–high
  range (194–239 mm/m for `ks-field-2`) is the survey's documented range, **not a statistical interval**.
- Root depth comes from the crop, not the soil, and is not part of the soil data.
- SoilGrids (non-US sites) is a model prediction with **very wide uncertainty**. No AWC interval is available, so
  sensitivity uses a declared ±20 % assumption.

## Satellite seasons (MODIS)
- Detected seasons are **suggested growing periods from canopy greenness**. Say "green-up", never "planting
  date". For winter wheat the detected start is spring green-up, not autumn sowing.
- The satellite **does not identify the crop**. Crop names come from the USDA crop map.
- **Low greenness is not proof of bare soil**: harvest residue, cloud or crop type can explain it. Say
  "possible low vegetation cover".
- Cloud- and snow-affected composites are kept but never used. Gaps longer than 32 days are not bridged.
- Autumn growth of newly sown wheat can appear as a short extra season.
- In wheat years the field shows a **second green-up after harvest** (a likely double crop or regrowth),
  unconfirmed locally.

## Validation: what has and hasn't been tested
- Season starts were checked against **statewide** USDA planting dates, not this field's: **5 of 5** corn
  seasons found, green-up **+22 days** after planting on average (tuning, n = 5); development check n = 2,
  **too few to judge**.
- Winter wheat and double-crop starts are **not validated**.
- The held-out years **2020–2025 have not been evaluated yet**. They are used once, at feature freeze.
- **Weather-range coverage is not evaluated yet** (it needs the simulation ensemble). Until it is, p10–p90 is
  a **"central 80% simulation range"**, never "confidence" or "prediction interval".
- Weather-coverage results, when they exist, say nothing about whether the crop or water model is right.

## Never claim
Yield, profit or soil-carbon numbers · that the app predicts the future climate · that satellite data shows
planting dates, crop types or bare soil · that NASA endorses the tool · accuracy beyond the measured numbers above.

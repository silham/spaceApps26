# Crop & soil catalog (owner: M4)

One JSON file per crop: `{"profile": <CropProfile contract>, "engine_extras": {...}}`.
Every parameter needs `value`, `unit`, `reference`, `region_relevance` and `uncertainty`.
Unknown values stay `null`; the claim that depends on them is blocked. Never fill them with a guess.

The current crop files are **ILLUSTRATIVE** FAO-56 generic table values (maize, grain sorghum, winter wheat)
used for the DEMO run. They are **not** the D4 crop set, which is still open (`docs/decisions.md`).
Replace or confirm them with M5 and local contacts.

- `engine_extras.max_height_m`: FAO-56 Table 12 crop height, needed by the Kc climate adjustment
  (FAO-56 eq. 62/65). Not in the `CropProfile` contract yet (proposal for M1).
- `engine_extras.tr55_cover`: TR-55 Table 2-2b cover class used to pick the runoff curve number.
- `soil_textures_fao56.json`: FAO-56 Table 19 ranges, used only as a DEMO soil assumption until the
  site soil profile from M3 (D8) is available.
- `curve_numbers_tr55.json`: TR-55 Table 2-2b curve numbers, checked against the 1986 document (p. 2-6).
- `winter_wheat_ks.json` (D4): winter wheat for `ks-field-2` with the FAO-56 Table 12 Kc, root depth, p and height,
  and a **Kansas-local season length** in `engine_extras.local_calendar`. The source is USDA NASS Kansas planting and
  harvest dates, split in the FAO-56 Table 11 Idaho proportions 160:75:75:25. `season_days` and `reference` are
  **null until the NASS dates are entered**, so the crop is infeasible until then. A length without a reference is
  rejected. Fill it with `uv run python scripts/derive_wheat_season.py --write` (needs `NASS_API_KEY`).

# Model documentation

Owner: M4. Engine version `0.3.0` (`ftm.engine.ensemble.MODEL_VERSION`).

Main references:
- Allen, Pereira, Raes & Smith (1998), *Crop evapotranspiration*, FAO Irrigation and Drainage Paper 56 ("FAO-56"), https://www.fao.org/4/x0490e/x0490e00.htm. Source ID `lit-fao56-1998`.
- USDA SCS (1986), *Urban Hydrology for Small Watersheds*, TR-55, 2nd ed. Source ID `lit-usda-tr55-1986`.

**Status.** Everything in "Implemented" is code with tests in `backend/tests/engine/`.
- **Primary site `ks-field-2`** (D3, resolved): real POWER weather from the DB works end to end. The SSURGO soil and the D4/D5 strategies are wired in.
- **Kansas wheat season length is filled (D4):** median 268 days (36 seasons harvested 1984–2019, range 249–287) from USDA NASS Crop Progress, statewide not field-level, source `nass_5f3d5f6af6a82ee7`. Stage lengths 128/60/60/20 days. All three ks-field-2 strategies fit the 2027–2028 horizon. `--wheat fao56-idaho` runs the FAO-56 Idaho row as printed, for checking only.
- **DEMO runs** (`scripts/run_engine_demo.py`) use synthetic weather, a FAO-56 Table 19 soil and illustrative strategies.

---

## Implemented

### Entry point

`ftm.engine.runner.run_engine(EngineRequest) -> EngineOutput` takes the following inputs:
- site
- elevation, with a note on its source
- wide forcing frame and its weather `Source`
- `SoilSpec`
- cited crop catalog
- strategies
- horizon
- mode and allocation
- initial condition
- paths and seed, or replay years
- the declared sample pool (`pool_range`, e.g. 1984–2019)

`validate_request` rejects a request, with a readable `EngineInputError`, when any of these holds:
- the forcing breaks the contract
- the forcing source does not match the declared weather source
- the elevation is missing
- the horizon is reversed
- there are no strategies, the strategy IDs are duplicated, or a strategy belongs to a different site
- the run is `fixed_allocation` without an allocation, or `irrigation_needed` with one
- the initial fraction is outside [0, 1]
- `n_paths` < 1
- the sample pool is reversed, or holds no usable season (the run is blocked)

`EngineOutput` holds:
- a `SimulationRun`, whose `input_versions` carry the weather processing-run ID, the soil profile ID, the crop-catalog SHA-256, the elevation, the initial condition, the irrigation rule and the ensemble config: block definition, horizon, sample pool, held-out years, path count, seed, method. `sample_period` is the sample pool period.
- one `Result` per strategy × metric
- the per-strategy `Feasibility`
- the block pool, replay windows and SIMULATE `JourneyStage`
- the limitations and the ET0 method counts

Every `Result` carries:
- `source_ids`, covering the weather source, the soil sources, `lit-fao56-1998` and `lit-usda-tr55-1986`
- `limitations` and `is_demo`
- `trace_path` when Parquet traces are written (`results/<run_id>/<strategy>.parquet`)

Infeasible strategies get results with `null` values, `sample_count = 0` and their reasons. They are never dropped silently.

### Forcing contract

`ftm.engine.forcing.assert_forcing_contract` checks the wide daily frame proposed to M3 on PR #2:

- **Index:** a complete `DatetimeIndex` named `date`. An absent day is a NaN row.
- **Required columns:** `<VAR>` and `<VAR>__flag` for `PRECTOTCORR`, `T2M_MAX`, `T2M_MIN`, `ALLSKY_SFC_SW_DWN` and `WS2M`.
- **Humidity:** at least one of `T2MDEW` and `RH2M`.
- **Provenance columns:** exactly one `source_id` and one `processing_run_id`. Two rainfall sources are therefore never summed.
- **Usable values:** only values flagged `ok` or `estimated` are used. A NaN with a usable flag is rejected.
- **Units:** POWER AG units, with no conversion.

**M3 store frame.** `from_store_frame` adapts `ftm.data.forcing.get_daily_forcing` output without changing values. That frame has an index of `datetime.date` and keeps `source_ids`, `processing_run_id` and `units` in `frame.attrs`. The adapter:
- converts the index to a `DatetimeIndex`
- copies the provenance into columns
- checks every engine variable's unit against the expected unit, raising an error on a mismatch and never converting

It is tested with M3's own `to_wide` pivot.

### Reference evapotranspiration (`engine.et0`)

1. **Penman–Monteith:** `pyfao56.refet.ascedaily('S', …)`, the ASCE standardized short reference, equal to FAO-56 eq. 6 at a daily step.
   - Tested against FAO-56 Example 18 (3.9 mm/day).
   - Actual vapour pressure comes from dew point (eq. 14) or, failing that, mean RH (eq. 19). It is returned as `ea_kpa`.
   - Inputs are flag-checked first because `ascedaily` silently substitutes Tdew = Tmin − 2 °C and u2 = 2 m/s.
2. **Hargreaves (eq. 52), per day:** used when Rs, wind or humidity is unusable but the temperatures are usable.
   - Ra comes from eqs. 21–25 and is multiplied by **0.408** (eq. 20). This is tested against Example 8 (Ra = 32.2).
   - The method used each day is recorded and counted.
3. **Unusable Tmax/Tmin:** ET0 is NaN and the block is excluded.
4. **Elevation:** required. Farm elevation is preferred; the POWER grid-cell elevation is the disclosed fallback.

### Soil-water balance (`engine.water_balance`)

This is a single-coefficient balance (FAO-56 ch. 8) on a profile of depth D, the depth over which soil AWC is known (1.0 m in M3's adapters).

**Why not `pyfao56.Model`:** it is dual-coefficient with one crop per run. The contracts carry single Kc, and rotations need fallow periods and storage carried across crops.

**Two stores:**
- The **active zone** has depth Zr: the crop root depth, or Ze on bare soil. TAW_r = AWC·Zr (eq. 82 per unit depth).
- The **subsoil** sits below it, with TAW_s = AWC·(D − Zr).
- **When Zr changes,** water moves in proportion to the depth that changes hands, assuming uniform content within a store. Water is conserved (tested).

| Step (daily) | Equation | Source |
|---|---|---|
| Runoff | RO = (P − 0.2S)²/(P + 0.8S) for P > 0.2S; S = 25.4(1000/CN − 10) mm | TR-55 eqs. 2-3, 2-4 (tested against Table 2-1: CN 80 gives 0.08 in from 1 in, 2.04 in from 4 in) |
| Infiltration | P − RO, into the active zone | |
| Irrigation | crop days with rule `refill_to_field_capacity_at_raw`: if depletion > RAW = p·TAW_r, refill to field capacity (net, 100% efficiency) | stated management rule |
| p | p = p_table + 0.04(5 − ETc), clipped to 0.1–0.8 | FAO-56 Table 22 footnote 2 |
| ETc | Kc·ET0 | FAO-56 eq. 56 |
| Ks | crop days: 1 if Dr ≤ RAW, else (TAW − Dr)/((1 − p)TAW); bare soil: 1, because the bare-soil Kc already includes drying | FAO-56 eq. 84 |
| AET | min(Ks·ETc, active-zone water) | |
| Percolation / drainage | excess above TAW_r goes to the subsoil; excess above TAW_s is deep drainage | FAO-56 eq. 88 |

**Mass balance (tested, exact, property-based):** ΔS = infiltration + irrigation − AET − deep drainage, where S is the active zone plus the subsoil. Both stores stay within [0, capacity]. NaN rain or ET0 raises `ForcingGapError` and is never treated as 0.

### Irrigation modes

- **`irrigation_needed`:** the rule above, uncapped. The output is the irrigation the rule requires. There is no shortfall metric.
- **`fixed_allocation`:** the same rule, capped by the remaining allocation per crop season.
  - Once the allocation is exhausted the crop goes into stress and never gets extra water (property-tested: seasonal irrigation ≤ allocation).
  - `allocation_shortfall_days` counts the days the rule could not deliver.
- **Rainfed cases:** fallow seasons and seasons with `irrigation_rule = null` get no irrigation. Any other rule string is infeasible, never silently replaced.

### Crop coefficients and fallow (`engine.kc`, `engine.rotation`)

**Crop Kc**
- Kc follows the FAO-56 eq. 66 curve, with Kc_end held from maturity to harvest. This is a declared assumption.
- **Kc_mid** is adjusted with eq. 62 to the path's mean u2 and RHmin over the mid stage. RHmin = 100·ea/e°(Tmax), and the inputs are held to the validity ranges (u2 1–6 m/s, RHmin 20–80 %, h 0.1–10 m). This is tested against **Example 27**: Taipei 1.07, Mocha 1.30.
- **Kc_end** is adjusted with eq. 65 over the late stage, but only when Kc_end > 0.45.
- If a stage has no usable wind or humidity, the table value is used and the run says so.
- **Kc_ini** is the FAO-56 Table 12 value.

**Fallow and bare soil (FAO-56 ch. 11, Annex 7)**
- On fallow, Kc = Kc_ini from eq. 7-3 / 7-4, with the Fig. 29 parameter set (light events, TEW 10, REW = min(max(2.5, 6/√ET0), 7)).
- The Fig. 30 set is used for large events:
  - coarse soils: TEW = min(15, 7√ET0), REW = min(6, TEW − 0.01)
  - medium and fine soils: TEW = min(28, 13√ET0), REW = min(9, TEW − 0.01)
- Infiltration depths between 10 and 40 mm are interpolated with eq. 59.
- Wetting events count infiltration ≥ 0.2·ET0, and events on adjoining days count as one.
- The wetting interval and ET0 are averaged per fallow period of at most 30 days. This is an engine method choice that follows the seasons.
- The active depth is Ze = 0.15 m (FAO-56 ch. 7: 0.10–0.15 m). Water below it is kept for the next crop.
- **FAO-56 Example 7-1 check:**
  - The Fig. 30a case reproduces exactly (0.75).
  - For the Fig. 29 case the page prints 0.57, but its own printed inputs in its printed eq. 7-3 evaluate to **0.533**.
  - The interpolation line prints "0.33(0.12)", where 0.75 − 0.57 = 0.18.
  - The engine implements the equation, and the test asserts 0.533. Both slips were checked against the page on 2026-11-14 and are flagged for M5.
- The page's "If t1 < tw then Kc ini = 1.15" contradicts its own eq. 7-4 condition. We follow eq. 7-4 (tw ≤ t1 gives 1.15), which is consistent with Example 7-1.

**Root depth and runoff cover**
- Root depth is the catalog maximum (FAO-56 Table 22) from planting, **capped at the soil data depth** (1.0 m). There is no root-growth model. The cap is disclosed in every affected result.
- Curve numbers come from the TR-55 Table 2-2b cover class:
  - row crops, straight row, good: 78
  - small grain, straight row, good: 75
  - fallow bare soil: 86
- These are the HSG B values. HSG B is assumed for silt loam from TR-55 Appendix A.

### Feasibility (hard constraints only)

Each failed constraint comes back as a readable reason:
- soil AWC is missing
- a season ends before it starts
- a season falls outside the horizon
- seasons overlap
- the crop is unknown, or not available to the farm
- a cited parameter is null, including `max_height_m`
- the season is shorter than the stage sum
- planting falls outside the crop's window
- the irrigation rule is not supported
- a fallow season is irrigated
- residue management is set, which is not modelled yet

### Ensemble, replay, pairing, determinism (`engine.ensemble`)

- **Blocks:** agricultural years anchored on the horizon start.
  - A block with any unusable rain day or any NaN ET0 day is **excluded with its reason**. Days are never skipped, because a skipped day would act as 0 mm rain.
  - The run is blocked only if no usable block remains.
- **Sample pool (validation plan v1.2 §1):** the bootstrap draws only from `pool_range`.
  - For ET₀ targets the pool is **1984–2019**. POWER has no solar radiation before 1984, so 1981–1983 would otherwise get Hargreaves ET₀ on every day; they are *not* excluded by the data check, only by the pool.
  - **2020–2025 are held out.** They can be replayed on screen (with a limitation saying so) but never build or tune a range.
  - The runner reports Hargreaves days that fall inside the pool.
- **Bootstrap:** independent years drawn by `numpy.random.default_rng(seed)`. The same inputs and seed give identical results (tested).
- **Coverage helper:** `ensemble_weather_paths(forcing, et0, EnsembleConfig)` returns exactly the weather paths a run with that config uses (tested equal to a run's paths). M5's coverage evaluation can rebuild the ensemble per held-out year.
- **Replay (`run_replay`):** one consecutive window, for example "replay 1995–1996". A window crossing an excluded year is refused with its reason, never shortened or swapped.
- **Pairing:** one weather frame per path is shared by every strategy (tested).
- **Warm-up:** each strategy is first run over the path's first block from the declared initial fraction of field capacity, and the main run starts from that end state.
- **Ranges:** p10/p50/p90 with sample count, labelled "central 80% simulation range (p10–p90)".
  - Below **20 paths** p10 and p90 are `null`. This is an engine choice, because one path per tail is too few, and M5 may revise it.
  - Replay has a single path, so it reports p50 only.

### Metrics

| Metric | Unit | Meaning |
|---|---|---|
| `irrigation_mm` | mm | net irrigation over the horizon |
| `allocation_shortfall_days` | days | fixed allocation only: days the rule could not deliver |
| `water_stress_days` | days | crop days with Ks < 1 (modelled stress, not yield) |
| `aet_mm` | mm | actual ET |
| `deep_drainage_mm` | mm | water leaving the bottom of the profile |
| `runoff_mm` | mm | TR-55 runoff |
| `cover_days` | days | crop in the ground, excluding the FAO-56 initial stage |
| `possible_low_cover_days` | days | fallow plus initial stage: *possible* exposure, not observed bare soil |
| `crop_diversity_count` | crops | distinct crops in the horizon |

**Not emitted (unsupported):** yield, profit, soil carbon change, nitrogen, salinity, erosion and residue cover.

### DEMO harness (`engine.demo`, `scripts/run_engine_demo.py`)

- **Synthetic weather:** `demo-synthetic-forcing` is deterministic synthetic weather (seed 20261114) with one missing-rain day in 2004 to show block exclusion. It is a separate source from `demo-weather` in `data/fixtures/demo.json`, and it never feeds or replaces that file's fake results.
- **DEMO elevation:** 800 m, part of the synthetic scenario rather than a surveyed site.
- **Strategy IDs:** `engine-demo-*`.
- `--power LAT LON` uses real POWER data through M3's adapter. The outputs stay DEMO because the soil and strategies are still DEMO.

### Sensitivity and coverage adapters for M5 (validation plan §3–4)

M5 owns the analyses in `ftm.validation.sensitivity` and `ftm.validation.coverage`: the scenarios, the rankings, coverage scoring and the test-year lock. The engine supplies the two callables they expect.

**Sensitivity: `engine.sensitivity.make_run_fn(base) -> run_fn(inputs) -> {strategy: {metric: p50}}`**
- `apply_inputs` maps M5's factor names onto the request:
  - `awc_mm_per_m` replaces the soil AWC, and the change is disclosed
  - `initial_soil_water_frac_taw` sets the initial fraction of field capacity
  - `planting_shift_days` moves every crop season, harvest included; fallow stays
  - `irrigation_allocation_mm` is accepted in fixed-allocation mode only
  - any other key is an error
- **Pairing:** every call keeps the seed, pool, horizon and path count, so every scenario draws **the same weather paths**. This is checked on each call, and a mismatch raises an error. Tested with M5's `one_at_a_time` and `ranking_stability`.
- A shift that breaks a hard constraint makes that strategy infeasible with its reason. It is then absent from that scenario's medians, never moved back silently.

**Coverage: `engine.ensemble.seasonal_ensemble_fn(forcing, et0, window, target, n_paths, seed) -> ensemble_fn(pool_years, target_year)`**
- Targets: `rain_mm`, `et0_mm`, `rain_minus_et0_mm`.
- It uses the same season-aligned block bootstrap with a one-season horizon: whole historical seasons are drawn with replacement from the pool by `default_rng(seed)`.
- A season with any unusable day is never drawn.
- A pool year at or after the target year is refused, so there is no leakage.
- Tested with M5's `rolling_origin`.

### Planting calendar and ks-field-2 strategies (`engine.calendar`, `engine.scenarios`)

**FAO-56 Table 11 footnote 2 rules**, applied to the site's own POWER temperatures over the sample pool:
- **Maize:** spring planting on the first day from 1 Feb on which the trailing 10-day mean of (Tmax + Tmin)/2 is ≥ 13 °C.
- **Winter wheat:** autumn sowing on the first day from 1 Aug on which that mean is ≤ 17 °C, or on 1 Dec, whichever comes first.
- The strategy calendar uses the median day across pool years, and the spread is reported. A year with a temperature gap in the window gives no date, never a filled one.
- At ks-field-2 over 1984–2019: maize **10 Apr** (p10–p90 of years 21 Mar – 28 Apr; earlier than typical Kansas practice, because the rule fires at the first spring warmth) and wheat **7 Oct** (24 Sep – 15 Oct).

**Grain sorghum** has no FAO-56 rule.
- The main-season planting date of **1 Jun** is an M4 scenario choice inside the FAO-56 Table 11 "May/June" planting period.
- The double crop is planted the day after the wheat harvest.

**D5 strategies:**
- **Baseline:** irrigated corn, then irrigated winter wheat.
- **Alternative A:** the baseline plus rainfed double-crop sorghum.
- **Alternative B:** rainfed sorghum, then irrigated wheat.
- Seasons end at maturity (the stage sum). Frost and harvest logistics are not modelled.

**Kansas wheat (`winter-wheat-ks`, D4).**
- It uses the FAO-56 Table 12 Kc, root depth, p and height.
- Its stage lengths come from `engine_extras.local_calendar`: a cited season length split 160:75:75:25 (the FAO-56 Idaho row's proportions), with the rounding put into the last stage.
- A season length without a reference is rejected.
- Filled 2026-11-14: 268 days → 128/60/60/20 (ini/dev/mid/late). If the length were null, every strategy using this wheat would be infeasible: "missing cited parameters (stage_lengths_days.*)".
- `scripts/derive_wheat_season.py --write` fills it from USDA NASS Crop Progress through M3's adapter. It takes the median of statewide 50 % planted to 50 % harvested over seasons harvested 1984–2019; held-out years are never read. It needs `NASS_API_KEY`.

**Site run:** `scripts/run_engine_site.py --site-id ks-field-2 --weather-source <id>`. It reads the site, weather source and soil profile from the DB, and the POWER grid elevation (858 m) from the raw snapshot. It stops if anything is missing.

---

## Planned / not implemented

- Root growth (FAO-56 eq. 8-1 style). Water below 1.0 m is ignored because soil data stops there.
- A Kc_ini from the Annex 7 procedure during the crop initial stage. Today this uses the table value.
- Residue and mulch effects: the FAO-56 ch. 11 "5% per 10% cover" reduction, and residue curve numbers.
- Antecedent-moisture curve-number adjustment, snow and frozen soil.
- Parameter-uncertainty draws: ranges today reflect weather variability only.
- Ks evaluated on the previous day's depletion. Today it is evaluated after the same day's water inputs.
- Paddy or ponded conditions (guide section 3), and capillary rise.
- The SSURGO hydrologic soil group. Today it is inferred from texture (TR-55 Appendix A) and disclosed. M3 could add `hydgrp` to the SDA query.

## Proposals to M1 (contracts are not changed by M4)

- **`Site.elevation_m`:** a field for the site elevation (with its source). Today the elevation is passed in `EngineRequest`.
- **`CropProfile.max_height_m`:** today this lives in `engine_extras` in the catalog JSON.
- **Soil fields on `SoilProfile`:** the data depth, the TR-55 hydrologic soil group and the Annex 7 texture class. Today these live in the engine-local `SoilSpec`.
- **`SimulationRun.allocation_mm`:** documented as millimetres per irrigated crop season, which is how the engine uses it.
- **`Result`:** no change needed. `trace_path` and `limitations` are used as designed.

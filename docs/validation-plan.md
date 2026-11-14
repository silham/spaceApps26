# Validation plan (pre-registered)

Owner: M5 · Written: 2026-11-14, **before any evaluation results were produced** · Status: v1

This plan fixes the targets, references, data splits and reporting rules *in advance*, so nobody can
choose them after seeing results (DEVELOPMENT_GUIDE.md §8). Any change after this date goes in the
change log at the bottom with a reason, and that reason must not be "the results looked bad".

Site (D3) and validation references (D10) are still open. Everything here is written relative to "the
site" and applies to whichever site is chosen. Items that depend on D3/D10 are marked **[site]**.

## 0. What we evaluate, and what we don't

| # | Question | What kind of check it is | Independent? |
|---|---|---|---|
| A | Do engine outputs obey physics and logic? | Unit/property tests (M4 owns, M5 reports) | n/a: correctness |
| B | Do detected growing seasons match real calendars? | Phenology vs farmer/local records | Yes, if the reference is independent of MODIS |
| C | Does the weather ensemble's range cover what actually happened? | Held-out weather coverage | Yes for weather; **not** crop/water-model validation |
| D | Does the strategy ranking survive uncertain inputs? | Sensitivity analysis | n/a: robustness, not accuracy |
| E | Do modeled soil-water dynamics agree with another product? | Consistency check vs SMAP L4 / GWETROOT | **No**: shared forcing (see §5) |

Things we will **not** call validation:
- Rerunning our own water model on a held-out year and comparing it to itself (guide §8.4).
- p10–p90 coverage before it has been measured. Until then it is a "central 80% simulation range".
- Any yield, profit or soil-carbon figure. We have no model or data for these.

## 1. Data splits (shared by B and C)

POWER daily coverage starts 1981. MODIS MOD13Q1 v061 starts February 2000. Today is 2026-11-14, so
2025 is the last complete year.

| Period | Years | Used for |
|---|---|---|
| Sample pool / tuning | 1981–2014 for rainfall, **1984–2014 for anything using ET₀** (weather) · 2001–2014 (MODIS) | Ensemble blocks are drawn from here; phenology parameters are tuned here |
| Development | 2015–2019 | Rolling-origin checks, choosing between methods, optional conformal calibration |
| **Final test, untouched** | **2020–2025** | Evaluated **once**, after feature freeze |

Rules:
- Test-period data may be *downloaded and quality-checked* (the pipeline has to see it to report
  gaps), but no evaluation, tuning or plotting of evaluation metrics touches it before unlock.
- The evaluation code enforces this with an explicit `unlock_test=True` argument, off by default.
- Unlock happens once, at H34–H36, after the methods are frozen. The commit hash at unlock is recorded
  in the Validation record. Results are reported whatever they show, including failures.
- MODIS year 2000 is excluded because it is incomplete (the record starts mid-February).
- POWER has no solar radiation before 1984 (found 2026-11-14, see change log), so ET₀ and the
  water balance cannot be computed for 1981–1983. Targets that use ET₀ start their pool in 1984.
- **Suspect source years [site]:** if a year is flagged by the explorer's screening rule (rain below
  50% of the site median *and* wettest day in the lowest 10% of yearly maxima), the team decides
  before any evaluation whether to (a) exclude it from the sample pool or (b) keep it with a visible
  label. Either way it is disclosed. Currently flagged: Sri Lanka candidate 1995 and 1996; Kansas none.

## 2. Phenology: season detection (B)

**Method (to be implemented in `ftm.validation.phenology`):**
1. Input: MOD13Q1 NDVI (EVI as a secondary check) for the field's pixel(s), scale factor applied, only
   points that pass QA (SummaryQA good/marginal; the exact QA bits are documented in the adapter).
2. Smoothing: `scipy.signal.savgol_filter` on QA-passed points resampled to the 16-day grid. Gaps are
   not bridged beyond 2 composites (32 days).
3. Season start/end: the date the smoothed curve crosses a fraction *f* of that season's amplitude,
   rising (start) and falling (end); the peak is the local maximum. This is the amplitude-threshold
   method used in TIMESAT (Jönsson & Eklundh 2004, doi:10.1016/j.cageo.2004.05.006).
4. Tuned on 2001–2014 only, choosing from a small declared grid: SG window ∈ {5, 7, 9} composites,
   polynomial order ∈ {2, 3}, *f* ∈ {0.2, 0.3, 0.5}. Selection criterion: lowest median absolute
   start-of-season error vs the reference. The grid is declared now so nobody can widen it later.

**Fallback (disclosed in the UI) when the signal is too weak.** These are declared heuristics, not
standards: in a season window, fewer than 50% of composites pass QA, **or** the seasonal NDVI
amplitude is < 0.1. Then the local calendar is shown instead, labelled as a fallback.

**Reference [site, D10]**, best first:
1. Farmer planting/harvest records for the field (if obtained).
2. Kansas: USDA NASS Crop Progress (state or district weekly % planted/harvested; the reference date
   is when 50% is reached). Limitation: regional, not field level.
3. Sri Lanka: Department of Agriculture Maha/Yala season calendar. These are windows, not per-year
   dates, so the metric becomes "inside window / days outside".

**Metrics:** bias and median absolute error (days) for start and end; detection rate (detected /
expected seasons); count of extra detected seasons; number of seasons *n*. Reported for the tuning
period and the test period separately.

**Stated limitations:** a MOD13Q1 pixel is 250 m (about 6 ha), the same order as the field, so mixed
pixels are likely. Low NDVI ≠ bare soil. Detected seasons never identify a crop species or an exact
planting date.

## 3. Weather-ensemble coverage (C)

**What is evaluated:** whether the ensemble's central 80% range (p10–p90), built only from the sample
pool, contains the held-out *observed weather* quantity.

**Targets** (weather-derived, per crop season window **[site]**):
1. Seasonal rainfall total (POWER PRECTOTCORR, mm).
2. Seasonal reference ET total (FAO-56 Penman-Monteith from POWER, computed with M4's implementation, mm).
3. Seasonal climatic water balance, rainfall − ET₀ (mm).

These are properties of the weather, not of our crop model. A good score here says the resampled
weather is a plausible spread. It says **nothing** about whether irrigation or stress outputs are right.

**Procedure:**
- Development: rolling origin. For each year *t* in 2005–2019, build the ensemble from 1981…*t*−1 (1984…*t*−1 for ET₀ targets) and
  check year *t*. This gives about 15 seasons per target to debug with.
- Final test: ensemble from 1981–2019 (1984–2019 for ET₀ targets), evaluated on 2020–2025 (6 years × seasons per year).
- The resampling method (season-aligned block bootstrap + consecutive-year replay) and seed come from
  M4's ensemble config, and are recorded in the Validation record.

**Metrics:**
- Empirical coverage: the fraction of held-out seasons inside [p10, p90]. Nominal is 0.80.
- Clopper-Pearson 95% interval on that fraction (`scipy.stats.binomtest(...).proportion_ci()`).
- Mean interval width (mm) and the number of seasons *n*.

**Pre-declared reading:**
- The CI upper bound < 0.80 → report "under-covers". The CI lower bound > 0.80 → report "over-covers
  (ranges wider than needed)". Otherwise → "consistent with 80%, but *n* is small".
- With *n* ≈ 6–12 the interval will be wide. We say so plainly. Coverage is never promised for future
  climate.
- Non-stationarity check: report whether the test-period mean of each target lies outside the sample
  pool's p10–p90. A warming trend makes this likely for ET₀, and it is a known limitation of historical
  resampling.

**Optional conformal adjustment:** only if time allows, calibrated on 2015–2019, evaluated on 2020–2025.
Its nominal coverage is not promised, because of temporal dependence (conformal prediction under
non-exchangeability, https://jmlr.org/papers/v25/23-1553.html, cited in guide §12).

## 4. Sensitivity of the strategy ranking (D)

**Question for the demo:** "If our soil or management assumptions are off, would the recommendation change?"

**Inputs varied** (low / mid / high), with the same paired weather paths for every combination:

| Input | Range | Source of the range |
|---|---|---|
| Available water capacity (AWC) | provider uncertainty bounds | Soil source **[D8]**; if none, ±20% labelled as an *assumption* |
| Initial soil water | 25 / 50 / 75 % of TAW | Declared assumption (start state unknown) |
| Planting date | −14 / 0 / +14 days, within the allowed window | Local calendar |
| Irrigation allocation (fixed-allocation mode) | −20 / 0 / +20 % | Declared assumption; farmer-confirmed value is the mid point |

**Method:** one-at-a-time first (8 runs + baseline), then the full 3⁴ = 81 grid if runtime allows.
For each metric (irrigation need, stress days, cover days, low-cover days) record the order of the
three strategies by median.

**Output:** "Ranking unchanged in X of Y combinations; the input that flips it is …". The trade-off,
not a single winner, is the message.

## 5. Consistency check vs another soil-moisture product (E)

If SMAP L4 passes M3's access check: compare anomaly time series (each minus its own climatology) of
modeled root-zone storage vs SMAP L4 root-zone soil moisture, using Spearman correlation of daily or
pentad anomalies.

**This is not independent validation.** SMAP L4 assimilates observations into a land model driven by
GEOS forcing, and POWER meteorology comes from MERRA-2 (also GEOS). GWETROOT *is* MERRA-2. Shared
forcing inflates agreement. A 9 km SMAP cell versus a field-scale bucket is a large spatial mismatch.
If SMAP is unavailable, the Validate stage says "independent soil-moisture comparison: not available".

## 6. Reporting

- Each evaluation produces one `Validation` record with: target, reference, periods, sample count,
  metrics, failures, independence notes.
- The Validate Data Journey stage shows **one** chart per target (observed vs ensemble range for
  coverage; detected vs reference dates for phenology). Failed and unavailable checks show as such.
- UI wording rules (M5 reviews every string): "central 80% simulation range" until coverage is
  measured; never "confidence", "accuracy" or "prediction interval" unsupported by §3 results.

## 7. Open dependencies

- D3 site → season windows, which reference applies.
- D8 soil source → AWC range for §4.
- D10 validation references → §2 reference choice.
- M4: ensemble config (block definition, horizon, seed), ET₀ implementation.
- **M1, contract gap:** `Validation` has `calibration_period` and `test_period` but no training/tuning
  period, which guide §8.3 asks us to record. Proposed: add `train_period: tuple[date, date] | None`.

## Change log

| Date | Change | Reason | Results seen before change? |
|---|---|---|---|
| 2026-11-14 | v1 written | — | No |
| 2026-11-14 | ET₀-based pools start 1984 instead of 1981; added a pre-declared rule for suspect source years | Data availability: POWER solar radiation starts 1984; explorer (PR #5) flagged Sri Lanka 1995–1996 rainfall as suspect | No: only data availability and quality were looked at, no evaluation was run |
| 2026-11-14 | §2 reference made concrete for the primary site `ks-field-2`: reference = USDA NASS Crop Progress **Kansas state-level** date when the crop reached **50 % planted** (linear interpolation between weekly reports), for the crop USDA CDL reports at the field that year. Scored: **summer crops planted in spring (corn, sorghum, soybeans)**, matched to the detected season whose peak falls in Jun–Sep of that year. Not scored: winter wheat (NASS planting is autumn; detected start is spring green-up) and double-crop seasons after wheat (NASS state progress describes full-season crops). Tuning years = 2001–2014 ∩ CDL coverage (CDL starts 2006; 2007 missing) → corn 2006, 2008, 2010, 2012, 2014 (n = 5). Development check 2015–2019 reported without retuning (corn 2016, 2018). A positive bias is expected (canopy greening lags planting) and is reported, not corrected. | The plan named NASS Crop Progress but not how to handle crop identity, winter wheat or double crops; fixed now before any evaluation | No: only CDL crop labels and the NASS API response format were looked at; no detected-vs-reference comparison was computed |

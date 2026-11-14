# Farm Time Machine — Development Guide

Version 1.1 · 15 November 2026 · NASA Space Apps: Field Shift (1.1: seasonal outlook and real calendar, D16)

Status: agreed product direction; implementation stack, primary site, crop parameters, and final Figma design remain undecided. This guide combines the Farm Time Machine concept with the supplied Field Shift team research plan. It describes intended behavior, not completed implementation or validated results.

## 1. Mission

Help farmers see what the coming seasons may bring at their field (rain, temperature and soil water), rehearse crop rotations under that outlook, compare water and soil-protection trade-offs, and understand uncertainty before planting. Combine NASA environmental data, local soil information, crop characteristics, and farmer priorities. Support farmer and agricultural expert judgment.

Deliver a clear, working story: select a preset farm → inspect its history → confirm inputs → compare current practice and two alternatives → replay the same weather → inspect trade-offs and evidence → save a decision card.

## 2. Mandatory development rules

### Rule 1 — Use standard libraries

Use the chosen language's standard library and established, maintained libraries for common tasks such as dates, units, data parsing, numerical methods, geospatial processing, charts, accessibility, and testing. Do not reinvent available, reliable functionality. Keep dependencies minimal; record versions and licenses. Custom code should focus on project-specific rotation logic and interactions. Document and test any custom scientific method. This rule does not select a language, framework, database, mapping service, or hosting provider.

### Rule 2 — Always mention used data sources

Every map layer, chart, metric, recommendation, and export must identify its actual sources. Show a short source label beside the result and an expandable details view. In derived results, distinguish source observations, model/reanalysis data, farmer inputs, literature parameters, and simulated outputs. Label demo data visibly. Do not list a source as used if it was only considered.

Record dataset/provider, product/version, variable, units, native spatial and temporal resolution, date coverage, retrieval date, source URL or DOI, license/attribution, quality flags, processing version, and known limitations. Attach source IDs and processing-run IDs to outputs. Never imply NASA endorsement. External soil data must retain its actual provider attribution.

### Rule 3 — Follow the exact Figma UI when provided

Once a Figma file is supplied, treat its specified frames, components, typography, spacing, colors, icons, assets, dimensions, states, and interactions as the visual source of truth. Reuse design tokens and components. Do not redesign, substitute layouts, or silently approximate specified elements. Compare implementation screenshots with the supplied frames at matching viewport sizes.

The existing dashboard image is a concept only and does not override Figma. For unspecified responsive or interaction states, extend existing design patterns consistently and document the assumption. Surface genuine accessibility or feasibility conflicts for resolution instead of silently changing the design. Do not invent a Figma URL or claim fidelity before comparison.

### Rule 4 — Make the project fully visualizable, but keep it simple

Users must be able to inspect the complete journey from data collection through quality checks, cleaning, missing-value handling, alignment, feature extraction, simulation, validation, and final comparison. Provide a compact Data Journey view with progressive disclosure. Each stage needs one plain-language explanation, a status, a small useful visual, and access to source details. Do not build a complex workflow editor, expose raw logs as the main UI, or overwhelm farmers with equations.

## 3. Scope and non-goals

### Must ship

- One data-ready, locally reviewed preset site and four to six relevant crops.
- Current practice plus two feasible alternative rotations.
- Editable two- or three-season timeline; clearly show any longer simulation horizon.
- Farmer priorities separated from hard constraints.
- Historical replay using identical weather across strategies.
- Daily water accounting and documented crop-stage parameters.
- Soil-cover, low-cover exposure, and rotation-diversity indicators.
- Scenario ranges for uncertain modeled outcomes.
- Satellite-assisted season detection, or a clearly disclosed local-calendar fallback.
- Visible sources, limitations, processing steps, and validation results.
- Reproducible cached data and a reliable demonstration path.

### Should ship after the core works

- Up to 500 paired, five-year historical-weather paths, subject to runtime and convergence checks.
- Trade-off scatter view with outcome clouds.
- Sensitivity analysis for uncertain soil and management inputs.
- GPM or SMAP integration after an early access/quality checkpoint.

### Stretch / cut first

Long-term future-climate projections (decades; seasonal forecast odds are in scope, D16), second region, exact yield prediction, trained yield ML, voice support, complex 3D, radial calendars, and live custom-location APIs. No quantitative soil-carbon gain, pest reduction, or profit claim without a suitable model and evidence.

The primary site is selected after checking data, crop information, and farmer access. Western Kansas and Sri Lanka are candidates, not confirmed baselines. Flooded paddy needs ponding, percolation, drainage, and irrigation treatment; do not apply an upland bucket unchanged. Prefer an upland pilot if paddy behavior cannot be supported.

## 4. Product flow and interaction contract

### Observe

Select a preset; view field boundary, imagery, environmental timeline, and native data footprints. Confirm planting/harvest history, soil information, irrigation allocation, equipment, crop availability, and market/use constraints. Satellite signals suggest growing periods; they do not automatically identify crop species or exact planting dates.

### Experiment

Show three aligned rotation rows. Provide a bounded set of supported crop, planting-window, and irrigation choices. All strategies share a weather sequence and comparison horizon. The baseline remains visible and may be the preferred option. Explain why a rejected option violates a constraint.

Pause replay at a useful turning point. Let users change a supported input and rerun or select the matching precomputed scenario. Show the resulting benefit and disadvantage. Never update a chart cosmetically while retaining stale underlying results.

### Decide

Show typical modeled outcomes and scenario ranges, trade-offs, assumptions, missing information, and local-review questions. Let the farmer select a strategy and record their reason. Export a decision card with sources, model version, run ID, parameters, and limitations.

Hard constraints filter feasibility; priorities rank or organize feasible options. Examples: irrigation allocation and equipment are constraints; conserving water and increasing cover are priorities. Do not hide multiple objectives inside an unexplained score.

## 5. Data Journey: required visual inspection

| Stage | Simple visual | Information to show |
| --- | --- | --- |
| Collect | Source cards and coverage strip | Provider, variable, period, resolution, retrieved/cached status |
| Check | Quality summary and marked timeline | Expected/received observations, missing, duplicate, flagged and rejected counts |
| Clean | Raw/cleaned overlay | Unit conversion, rejected records, duplicate policy, processing reason |
| Handle gaps | Timeline with different markers | Original gaps, estimated values, unresolved gaps, chosen method |
| Align | Small footprint map and common timeline | Native resolutions, aggregation rule, timezone, retained QA |
| Extract | Vegetation curve and season markers | Detected growing periods, possible low cover, farmer corrections |
| Simulate | Water-storage trace and paired outcome ranges | Inputs, model mode, assumptions, seed, scenario count |
| Validate | One observed/model or coverage chart | Target, reference, split, sample count, interval width, failures |
| Compare | Three rotation cards and trade-off view | Benefits, disadvantages, uncertainty, source links |

Default to compact summaries; open detail on demand. Use no more than one main chart per stage. Provide readable legends, keyboard operation, color-independent status labels, and a short 'What does this mean?' explanation.

## 6. Data handling requirements

- Preserve an immutable raw snapshot and produce versioned processed outputs. Never overwrite source values with cleaned values.
- Preserve original timestamps; declare analysis timezone, units, aggregation boundaries, and leap-day handling.
- Missing rainfall is not zero rainfall. Do not interpolate missing rainfall as a default. Flag affected periods, exclude them with disclosure, or use a documented alternate source whose bias is assessed.
- Use variable-specific gap rules. Short continuous-variable gaps may be estimated only with a declared maximum gap, method, and estimated-value flags. Leave long gaps unresolved or use an explicit fallback.
- Decode quality flags and scale factors before analysis. Treat invalid negatives according to product rules, not blanket clipping. Distinguish duplicates, rejected records, and missing values.
- Keep observed, estimated, farmer-entered, reanalysis, and simulated values distinguishable in storage and visuals.
- Align data for computation without claiming resampling creates field-level detail. Preserve native footprint metadata.
- Use one declared rainfall source per run; do not sum POWER and GPM rainfall. For source switching, document overlap checks and coverage changes.
- A seasonal forecast (D16: ECMWF SEAS5 via Open-Meteo) is never used as weather in the water balance. It only weights which past years of the run's one weather source are drawn, from forecast anomalies taken against the forecast model's own hindcast climatology. Show its attribution and state that its skill is not evaluated at the field.
- Use quality-filtered MODIS or finer suitable imagery for phenology. Low vegetation is not proof of bare soil; irrigation, harvest, clouds, mixed pixels, or crop type may explain it.
- GWETROOT is a modeled/reanalysis quantity, not a direct field measurement. SMAP L4 also incorporates a land model. State these distinctions in evidence views.

## 7. Scientific engine requirements

### Water and crop model

Use documented reference evapotranspiration, stage-specific crop coefficients, root depth, available soil-water capacity, stress response, and management rules. Maintain daily accounting:

storage change = infiltrated rain + irrigation − actual evapotranspiration − drainage

Account for runoff separately when converting rainfall to infiltration. Keep storage physically bounded. Actual evapotranspiration must respect available water and the chosen stress formulation. Carry water between crop stages and seasons; declare initial conditions and warm-up. Do not claim modeled stress is observed stress.

Expose two modes: (1) irrigation needed under a stated management rule; (2) water stress under a fixed allocation. Do not silently provide unlimited water in mode 2. Validate units carefully. Hargreaves radiation must use the units required by the cited equation; if Ra is in MJ/m²/day, apply the appropriate conversion to equivalent evaporation. Use standard, tested implementations where available.

Crop parameters require cited sources, region/variety relevance, and uncertainty or limitations. Missing parameters block a supported claim or trigger a visible fallback; do not invent them.

### Rotation and soil protection

Carry state across crops. Respect duration, harvest/termination dates, equipment, and water constraints. Represent cover and residue management explicitly. Report cover duration, possible low-cover exposure, crop diversity, and documented agronomic opportunities. A cover crop can consume water needed by the next crop. Describe nitrogen-fixing potential and pest-cycle interruption conditionally; do not convert them into unsupported numerical gains.

### Simulation ensemble

Use identical weather and paired soil/management draws across strategies. Preserve within-block weather-variable relationships. Use season-aligned historical blocks and include consecutive-year replay to examine persistent drought. Independently sampled years do not preserve multiyear climate persistence. Record sample period, resampling method, seed, number of paths, horizon, parameter draws, and model version.

Target 500 five-year paths only after simpler replay works. Check numerical stability at smaller/larger path counts. Show p10/p50/p90 as a central 80% simulation range; it is not automatically a calibrated prediction interval. Keep weather variability separate from parameter uncertainty. Historical resampling is not a future climate projection.

For user farms (D16) the horizon is the real calendar: it starts the day after the last observed weather day. The first block's years are drawn with seasonal-forecast weights (tercile-conditioned resampling), blended with equal weights so that at least ten effective years remain; later blocks are drawn equally. The initial soil water is simulated from the last observed year under the crop the farmer reports on the field (bare soil otherwise, stated) instead of a declared fraction plus warm-up. Record the forecast source, weights, method and assumptions with every run.

## 8. Validation and credibility

1. Test units, mass balance, physical bounds, crop-calendar feasibility, shared forcing, carryover, and deterministic reproducibility.
2. Compare detected seasons with farmer records or local calendars and report timing differences and limitations.
3. Use chronological or rolling evaluation for weather coverage. Record train/calibration/test periods, held-out sample count, empirical coverage, and interval width.
4. Distinguish weather-coverage evaluation from crop/water-model validation. Recomputing deficit with the same model on a held-out year is not independent field validation.
5. Compare modeled outcomes with suitable independent observations when available. Record spatial mismatch and shared inputs between products.
6. Keep final test data untouched. Optional conformal adjustment uses separate calibration data; do not promise nominal coverage under temporal dependence or climate shifts.
7. Show unsuccessful checks and unavailable validation honestly. No fabricated accuracy, confidence, or yield numbers.

## 9. Stack-neutral architecture and contracts

Choose implementation technologies later based on team familiarity, scientific-library support, mapping/chart needs, performance, accessibility, licensing, and deployment reliability. Do not treat any earlier framework suggestion as a commitment.

Logical components: source adapters; raw cache; quality/cleaning pipeline; crop and soil catalog; scenario engine; validation module; result store; interface/export layer. These can share one codebase; microservices are not required.

Agree on these entities before implementation:

| Entity | Required fields / responsibilities |
| --- | --- |
| Site | ID, name, location/boundary, timezone, area, farmer-confirmed context |
| Source | ID, provider, product/version, URL/DOI, units, resolutions, license, dates, QA |
| Observation | Site/source IDs, timestamp, variable, raw value, processed value, quality and imputation flags |
| Processing run | ID/version, input IDs, steps, parameters, affected counts, outputs |
| Crop/soil profile | IDs, parameters, units, references, region, uncertainty, user overrides |
| Strategy | ID, ordered crops, dates, management, constraints, feasibility reasons |
| Simulation run | ID, input versions, mode, weather paths, seed, horizon, model version |
| Result | Strategy/run IDs, metric/unit, quantiles, traces, sample count, source IDs, limitations |
| Validation | Target, reference, split periods, sample count, metrics, failures, independence notes |

Separate raw, processed, demo, and real results. Version schemas. Precompute bounded demo combinations and cache all demo dependencies. Unsupported combinations must be disabled or explicitly computed; never substitute the nearest scenario silently. If map tiles need network access, include an appropriately licensed cached/static fallback. Do not promise a fully offline demo until verified.

## 10. Team responsibilities and delivery

- Data owner: acquisition, QA, gaps, provenance, cached inputs, Data Journey evidence.
- Engine owner: water accounting, rotation logic, paired scenarios, replay, model documentation.
- Validation owner: phenology checks, evaluation splits, sensitivity, uncertainty labels.
- Interface owner: exact supplied Figma, interactions, accessibility, data views, exports.
- Research/demo owner: local crop assumptions, references, first-user testing, pitch and documentation.

These are responsibility areas, not assumptions about team size. Assign named owners at kickoff; combine roles if needed.

| Checkpoint | Done means |
| --- | --- |
| H0–H2 | Site/strategies and contracts agreed; source access checked; labeled fixtures available |
| H12 | Real weather cached; one strategy runs; source/cleaning views work |
| H24 | Three strategies and replay work end to end; comparison consumes real outputs |
| H36 | Feature freeze; scenario ranges, evidence and validation ready; Figma checks completed where available |
| H44 | Demo recorded; documentation and export checked; backup tested |
| H44–H48 | Fixes and submission buffer |

Cut order: yield ML, arbitrary locations, second region, future projections, elaborate graphics, advanced trade-off plots. Protect three strategies, replay, truthful ranges, basic Data Journey, farmer constraints, and source disclosure. Arrange sustainable handoffs and rest; avoid a single-person dependency.

## 11. Definition of done

- [ ] Three strategies use the same forcing, horizon, and documented assumptions.
- [ ] Hard constraints work and unsupported edits are clearly handled.
- [ ] Collection, cleaning, missing values, alignment, extraction, simulation and validation are visually inspectable.
- [ ] Every displayed data product and exported result identifies actual sources.
- [ ] Raw/cleaned/imputed/simulated values remain distinguishable.
- [ ] Tests cover water balance, units, bounds, dates, paired comparisons and reproducibility.
- [ ] Uncertainty labels match what was evaluated; no fabricated validation claims.
- [ ] Provided Figma frames are followed and checked; unspecified states are documented.
- [ ] Main flow is understandable without technical expertise and works with keyboard controls.
- [ ] Demo, empty, loading, missing-data, failed-run and unavailable-scenario states are handled.
- [ ] Cached demonstration and backup have been rehearsed.
- [ ] Decision export includes sources, run/model versions, assumptions and local-review questions.
- [ ] Documentation describes setup, data, model, validation, UI, decisions and limitations.

## 12. References and source register starters

These are references to investigate/use, not a claim that all are integrated. Confirm product versions, availability, access, licenses, and parameter units before implementation.

- Challenge: https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/
- Introduction video: https://www.youtube.com/watch?v=cF0U2WXsM7o
- NASA POWER daily API: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
- MODIS MOD13Q1: https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1
- GPM IMERG V07: https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- SMAP L4: https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008
- OpenLandMap-soildb research (external soil source): https://doi.org/10.5194/essd-18-989-2026
- FAO-56 meteorological methods and Hargreaves units: https://www.fao.org/4/x0490e/x0490e07.htm
- Conformal prediction under non-exchangeability: https://jmlr.org/papers/v25/23-1553.html
- Team input: fieldshift_plan.pdf, Version 1, 14 November 2026, supplied by the team. Its proposed stack is intentionally not adopted; calibration promises, calendar detection claims, and dataset exclusions are qualified in this guide.

## 13. Decisions still open

Primary farm/site; verified local rotation options; soil information; exact crop parameters; technical stack; supported edit combinations; dataset access routes; Figma link and frame IDs; secondary region; optional validation references. Record each resolution with date, owner, rationale, and affected assumptions. Do not silently convert candidates into facts.

# M4 — Simulation Engine Engineer (+ crop research)

**Name:** _TBD_ · **Buddy:** M1

## Mission
Simulate daily water and soil cover for three rotations under identical weather, using cited parameters and physically correct accounting.

## Owns
`backend/src/ftm/engine/` (water balance, rotation logic, constraints, replay, ensemble), `backend/src/ftm/engine/catalog/` (crop/soil parameters with references), `docs/model.md`.

## Inputs → Outputs
- **In:** daily forcing + soil properties (M3), strategies and supported edits (M1/kickoff), local crop info (M5/local contacts).
- **Out:** SimulationRun + Result records with daily traces and quantiles (M1 API → M2), ensemble outputs (M5).

## Tasks

### H0–H4
- [ ] With M5, pick 4–6 crops for the site. For each: FAO-56 Kc (ini/mid/end), stage lengths, max root depth, depletion fraction p, plus planting window. Every value needs a citation, region/variety relevance and an uncertainty or limitation. Missing → `null` + blocked claim.
- [ ] Write the current practice + 2 alternative rotations as Strategy fixtures (with cover/fallow periods).
- [ ] Engine skeleton against DEMO forcing so tests run from H4.

### H4–H12
- [ ] ET0: FAO-56 Penman-Monteith from POWER variables via `pyfao56` (or the `pyfao56`-compatible path); Hargreaves fallback with Ra converted from MJ m⁻² day⁻¹ to mm day⁻¹ (×0.408).
- [ ] Daily root-zone water balance: runoff → infiltration, irrigation, AET with the stress coefficient Ks, deep drainage, storage bounded in [0, TAW]; warm-up and declared initial conditions.
- [ ] **H12: one strategy runs on real weather.**

### H12–H24
- [ ] Two modes: (1) irrigation needed under a stated rule; (2) water stress under a fixed seasonal allocation (allocation exhausted → stress, never extra water).
- [ ] Rotation engine: sequence, planting/harvest/termination dates, carry-over of storage between crops and seasons, cover/residue representation.
- [ ] Hard-constraint feasibility with readable reasons (irrigation allocation, equipment, crop availability, season length).
- [ ] Indicators: irrigation need / stress days, cover days, low-cover exposure days, crop diversity count.
- [ ] Replay output: per-day traces for all three strategies on the same weather.
- [ ] **H24: three strategies + replay end to end on real outputs.**

### H24–H36
- [ ] Ensemble: season-aligned block bootstrap of historical years plus actual consecutive-year replay; paired weather and parameter draws across strategies; seeded; record sample period, method, seed, path count, horizon, model version.
- [ ] Start at 50 paths; check stability at 50/100/200 before going to 500.
- [ ] p10/p50/p90 per metric; weather variability kept separate from parameter uncertainty.
- [ ] `docs/model.md`: equations, citations, assumptions, limitations.

## Outcomes (definition of done for M4)
| Outcome | Accepted when |
|---|---|
| Cited catalog | Every crop/soil parameter has a reference, units, region relevance and uncertainty; no invented values |
| Correct water balance | Tests prove mass balance to tolerance, storage bounds, unit conversions (incl. Hargreaves Ra), carry-over |
| Two honest modes | Fixed-allocation mode can never exceed the allocation; tested |
| Fair comparison | Tests prove all strategies share identical forcing, horizon and paired draws |
| Reproducible | Same inputs + seed → identical results; run metadata stored |
| Constraint feedback | Every infeasible strategy or edit returns a human-readable reason |
| Ranges | p10/p50/p90 per metric with sample count; labelled as a simulation range |

## Cut order (M4 area)
500 paths → 50–100; parameter uncertainty draws → weather-only with disclosure; three seasons → two.

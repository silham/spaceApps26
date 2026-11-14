# M5 — ML / Validation & Uncertainty Engineer (+ pitch)

**Name:** _TBD_ · **Buddy:** M3

## Mission
Detect growing seasons from satellite data, find out what the model's ranges actually support, and make sure nothing we show claims more than that.

> Scope note: there is **no yield ML** in this project (first item on the cut list). "ML" here means phenology signal processing plus uncertainty and validation methods.

## Owns
`backend/src/ftm/validation/` (phenology, calendar evaluation, coverage, sensitivity), the Extract and Validate Data Journey payloads, `docs/references.md`, the limitations text, the pitch (with M1).

## Inputs → Outputs
- **In:** quality-filtered MODIS VI series (M3), farmer records / local crop calendar, ensemble outputs (M4).
- **Out:** detected seasons + low-cover windows (M4, M2), validation payloads (M2), wording review (M2), references (everyone).

## Tasks

### H0–H4
- [ ] Gather local crop calendars / farmer records for the chosen site and help M4 with the crop parameters.
- [ ] Start `docs/references.md`: every citation the team uses, with DOI/URL.
- [ ] Define the validation plan: targets, references, chronological splits, and an untouched final test period. Write it down **before** looking at any results.

### H4–H24 Phenology
- [ ] Smooth the VI series (e.g. `scipy.signal.savgol_filter`) only on QA-passed points; record the method and parameters.
- [ ] Detect season start/peak/end (threshold or derivative method, cited); output suggested growing periods with confidence notes; never claim a crop species or exact planting date.
- [ ] Flag possible low-cover windows, with the caveat that low VI ≠ bare soil.
- [ ] Disclosed local-calendar fallback when the signal is too weak.
- [ ] Calendar evaluation: timing differences against farmer/local records (days early/late, n seasons).
- [ ] Extract-stage payload: VI curve, season markers, farmer corrections.

### H24–H36 Uncertainty & validation
- [ ] Weather-coverage evaluation: rolling/chronological splits; for the held-out years, empirical coverage of the simulation range and interval width; sample counts reported.
- [ ] Keep weather-coverage evaluation separate from crop/water-model validation. Recomputing deficits with the same model is not independent validation.
- [ ] Independent outcome comparison only if suitable observations exist (record spatial mismatch and shared inputs); otherwise state "not available".
- [ ] Sensitivity: vary soil AWC and the uncertain management inputs → does the strategy ranking change? This feeds the "memorable interaction".
- [ ] Validate-stage payload, including failed checks shown honestly.
- [ ] Review every uncertainty-related UI string and export field.

### H36–H48
- [ ] Limitations section, first-user test notes, pitch deck + script with M1.

## Outcomes (definition of done for M5)
| Outcome | Accepted when |
|---|---|
| Season detection | Detected periods for the site with method, parameters and QA filter recorded; fallback disclosed when used |
| Calendar evaluation | Timing differences vs farmer/local calendar reported with n and limitations |
| Coverage evaluation | Empirical coverage + interval width on untouched held-out periods with sample counts; no promised coverage before measurement |
| Sensitivity | Ranking stability under soil/management uncertainty shown for the demo scenario |
| Honest wording | No "confidence", "prediction interval" or accuracy claim unsupported by an actual evaluation |
| References | `docs/references.md` complete for every method and parameter used |
| Pitch | Deck + script rehearsed; claims match the validation results |

## Cut order (M5 area)
Conformal adjustment → drop; independent outcome comparison → "not available" statement; phenology → disclosed calendar fallback.

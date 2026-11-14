# M1 — Technical Lead

**Name:** _TBD_ · **Buddy:** M4 (API/engine), M2 (UI integration)

## Mission
Keep five people building one product. Own the architecture, the shared contracts, the API, integration quality and a demo that works on the day.

## Owns
`backend/src/ftm/contracts/`, `backend/src/ftm/api/`, `backend/src/ftm/provenance.py`, `contracts/`, `docker-compose.yml`, `Makefile`, `.github/`, `docs/decisions.md`, approval of all DB schema changes, the demo script and submission.

## Inputs → Outputs
- **In:** processed data and Data Journey stats (M3), simulation results (M4), validation payloads (M5), UI needs (M2).
- **Out:** contracts and generated types (everyone), API endpoints (M2), fixtures (M2, M4), decision log (everyone).

## Tasks

### H0–H2 Kickoff
- [ ] Run the kickoff. Record these decisions in `docs/decisions.md` with owner and rationale: primary site, 4–6 crops, current practice + 2 alternatives, supported edits (e.g. irrigation limit, planting window), stack confirmation, Figma link.
- [ ] Confirm the scaffold runs for everyone (`make up install migrate seed api web`).
- [ ] Finalise the v1 pydantic contracts for the 9 entities + DecisionRecord; run `make contracts`.
- [ ] Co-review the DB schema with M3; first migration merged.
- [ ] Commit DEMO fixtures (site, sources, 3 strategies, one fake result clearly flagged `demo: true`).

### H2–H12
- [ ] API routes backed by the DB: `/sites`, `/sources`, `/journey/{site_id}`, `/strategies`, `/runs`, `/results/{run_id}`.
- [ ] Provenance plumbing: every response that carries a result includes `source_ids`, `processing_run_id`/`simulation_run_id`, `model_version`, `is_demo`.
- [ ] CI green on `main` (lint, tests, contract freshness).

### H12–H24
- [ ] `POST /runs` for supported edits: validate against the supported-edit set, call the M4 engine, persist SimulationRun + Result. Unsupported → `422` with a reason, never a nearest match.
- [ ] Result caching keyed by (strategy, inputs hash, weather paths, seed, model version).
- [ ] Integrate the M2 screens with the real endpoints; remove the fixture fallback from the main path (keep it only for demo mode).

### H24–H36
- [ ] `/decision-card` export (JSON + PDF): chosen strategy, farmer's reason, sources, run/model IDs, parameters, ranges, limitations, local-review questions.
- [ ] Walk through the Definition of Done (guide §11) and log the gaps as issues with owners.
- [ ] **H36 feature freeze**: only fixes after this.

### H36–H48
- [ ] Demo script (≤ 4 min), rehearsed twice; record the backup video.
- [ ] Backup: `pg_dump` + static-file tarball, restored on a second machine with the network off.
- [ ] README setup instructions tested from a clean clone.
- [ ] Co-write the pitch with M5 and submit with buffer.

## Outcomes (definition of done for M1)
| Outcome | Accepted when |
|---|---|
| Decision log | Every open item from guide §13 is either resolved (date, owner, rationale) or explicitly still open |
| Contracts | One pydantic source of truth; generated JSON Schema + TS types in sync (CI-enforced) |
| API | All endpoints documented at `/docs`; each result response carries sources, run ID, model version and a demo flag |
| Supported edits | Unsupported combinations rejected with a human-readable reason; no silent substitution |
| Decision card | Export contains sources, run/model versions, assumptions, limitations and review questions |
| Reliability | Demo restores from backup on a clean machine; backup video recorded |
| Team health | No single-person dependency; handoffs documented; rest shifts staggered |

## Cut order (M1 area)
PDF export → JSON only; result cache → recompute; live rerun → precomputed supported edits only.

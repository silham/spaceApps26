# Team briefs

| ID | Role | Brief | Buddy (backup) |
|---|---|---|---|
| M1 | Technical Lead | [M1-tech-lead.md](M1-tech-lead.md) | M4 (API/engine), M2 (UI integration) |
| M2 | Frontend / Interface | [M2-frontend.md](M2-frontend.md) | M1 |
| M3 | Backend / Data | [M3-backend-data.md](M3-backend-data.md) | M5 |
| M4 | Simulation Engine | [M4-simulation-engine.md](M4-simulation-engine.md) | M1 |
| M5 | ML / Validation & Uncertainty | [M5-ml-validation.md](M5-ml-validation.md) | M3 |

Fill in names at kickoff. Each brief lists **tasks by checkpoint** and **outcomes**: what must exist and be true for the work to count as done. Hours (H) are counted from the start of the hackathon.

## Shared checkpoints

| Checkpoint | Team outcome |
|---|---|
| H2 | Site, crops, 3 strategies, stack and contracts agreed; data access verified; DEMO fixtures load |
| H12 | Real weather cached; one strategy runs; Collect/Check/Clean views show real data |
| H24 | Three strategies + replay end to end on real outputs |
| H36 | Feature freeze; ranges, evidence, validation, Data Journey complete |
| H44 | Demo recorded; docs + export checked; backup restore tested |
| H48 | Submitted |

## Handoff map

```
M1 contracts + fixtures (H2) ──► M2 UI shell, M4 engine skeleton
M3 processed weather (H12)   ──► M4 water balance
M3 MODIS series (H16)        ──► M5 phenology
M4 results + traces (H24)    ──► M1 API ──► M2 Experiment/Decide screens
M4 ensemble (H30)            ──► M5 coverage + sensitivity ──► M2 Validate stage
```

If a handoff will be late, tell the receiver and M1 straight away. They work on fixtures in the meantime.

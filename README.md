# Farm Time Machine

Rehearse the next crop rotation against historical weather and understand the trade-offs before planting.
NASA Space Apps Challenge 2026: *Field Shift: Adapting Farms with NASA Data*.

> Status: early scaffold. Not a validated system. Data shown is labelled DEMO until real sources are cached.

## Docs
- [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md): rules, science boundaries, definition of done
- [TEAM_PLAN.md](TEAM_PLAN.md) and [docs/team/](docs/team/): roles, tasks, outcomes
- [AGENTS.md](AGENTS.md): instructions for AI coding agents
- [docs/decisions.md](docs/decisions.md), [docs/data-sources.md](docs/data-sources.md), [docs/model.md](docs/model.md), [docs/references.md](docs/references.md)

## Quick start

Requires Docker, [uv](https://docs.astral.sh/uv/), Node 22+ and pnpm.

```bash
cp .env.example .env
make up          # Postgres + PostGIS
make install     # backend + frontend deps
make migrate     # create tables
make seed        # load DEMO fixtures
make api         # http://localhost:8000/docs
make web         # http://localhost:5173
```

`make test`, `make lint` and `make contracts` are described in [AGENTS.md](AGENTS.md#6-commands).

## Layout

```
backend/    FastAPI, SQLAlchemy/Alembic, data pipeline, engine, validation (Python 3.12)
frontend/   React + TypeScript + Vite
contracts/  JSON Schema generated from backend contracts
data/       raw (immutable, gitignored) / processed (gitignored) / fixtures (DEMO, committed)
results/    large run artefacts (gitignored)
docs/       decisions, sources, model, references, team briefs
```

## Data & attribution
Every chart and export names its actual sources. See [docs/data-sources.md](docs/data-sources.md). Use of NASA data does not imply NASA endorsement.

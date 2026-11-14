.PHONY: up down install migrate migration seed api web test lint format contracts backup

BACKEND := cd backend && uv run
FRONTEND := cd frontend && pnpm

up:            ## start Postgres/PostGIS
	docker compose up -d db

down:
	docker compose down

install:       ## install backend + frontend dependencies
	cd backend && uv sync
	$(FRONTEND) install

migrate:       ## apply DB migrations
	$(BACKEND) alembic upgrade head

migration:     ## create a migration: make migration m="add foo"
	$(BACKEND) alembic revision --autogenerate -m "$(m)"

seed:          ## load DEMO fixtures
	$(BACKEND) python scripts/seed_demo.py

api:           ## FastAPI on :8000
	$(BACKEND) uvicorn ftm.api.main:app --reload --port 8000

web:           ## frontend dev server on :5173
	$(FRONTEND) dev

contracts:     ## regenerate JSON Schema + TS types from pydantic contracts
	$(BACKEND) python scripts/export_contracts.py
	$(FRONTEND) run gen:types

test:
	$(BACKEND) pytest
	$(FRONTEND) run typecheck

lint:
	$(BACKEND) ruff check . && cd backend && uv run ruff format --check .
	$(FRONTEND) run lint

format:
	$(BACKEND) ruff check --fix . && cd backend && uv run ruff format .

backup:        ## pg_dump + static files tarball for the offline demo
	mkdir -p backups
	docker compose exec -T db pg_dump -U ftm -Fc ftm > backups/ftm.dump
	tar czf backups/static.tgz data results

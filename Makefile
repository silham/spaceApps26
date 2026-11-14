.PHONY: up down install migrate migration seed demo-load demo-restore api web test lint format contracts backup

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

demo-load:     ## load ks-field-2 (POWER, SSURGO, MODIS) and register its strategies; needs network + .env keys
	$(BACKEND) python scripts/load_site.py --site-id ks-field-2 --name "Kansas field 2 (irrigated pivot)" \
		--lat 38.01517 --lon -100.92496 --timezone America/Chicago \
		--boundary ../docs/site-search/ks-field-2.geojson --area-ha 45.8 \
		--status "primary site (D3); local confirmation pending" $(LOAD_ARGS)
	$(BACKEND) python scripts/seed_site.py --site-id ks-field-2

demo-restore:  ## restore the offline demo from backups/ (made by make backup)
	docker compose exec -T db pg_restore -U ftm -d ftm --clean --if-exists < backups/ftm.dump
	tar xzf backups/static.tgz

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
	$(FRONTEND) run test

lint:
	$(BACKEND) ruff check . && uv run ruff format --check .
	$(FRONTEND) run lint

format:
	$(BACKEND) ruff check --fix . && uv run ruff format .

backup:        ## pg_dump + static files tarball for the offline demo
	mkdir -p backups
	docker compose exec -T db pg_dump -U ftm -Fc ftm > backups/ftm.dump
	tar czf backups/static.tgz data results exports

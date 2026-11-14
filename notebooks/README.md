# Notebooks

Narrative walkthroughs for the team and judges. They **call the project's tested code** (`ftm.*`) and read
the same Postgres database as the app, so a notebook can never disagree with the app. Pipeline logic
lives in `backend/src/ftm/`, never in a notebook.

| Notebook | What it shows | Needs |
|---|---|---|
| `01_weather_eda.ipynb` | Collect → Check → Clean → Handle gaps → Align, then weather EDA (water gap by month, yearly series, suspect years, temperature trend) and soil profiles | DB with both candidate sites loaded |
| `02_season_detection.ipynb` | *(planned)* MODIS vegetation curves, smoothing, season start/end tuning on 2001–2014 | MODIS extraction (Earth Engine) |
| `03_validation.ipynb` | *(planned)* weather-range coverage, season timing errors, ranking sensitivity, failures included | M4 ensemble |

## Run

```bash
docker compose up -d db                     # project DB (see .env for the port)
cd backend
uv sync                                     # includes ipykernel, nbconvert, matplotlib (dev)
uv run alembic upgrade head
uv run python scripts/load_power.py --site-id cand-kansas --name "Candidate: western Kansas (near Garden City)" \
    --lat 37.97 --lon -100.87 --timezone America/Chicago --start 1981-01-01 --end 2025-12-31
uv run python scripts/load_power.py --site-id cand-sri-lanka --name "Candidate: Sri Lanka dry zone (near Anuradhapura)" \
    --lat 8.31 --lon 80.40 --timezone Asia/Colombo --start 1981-01-01 --end 2025-12-31
uv run python scripts/load_soil.py --site-id cand-kansas --source ssurgo
uv run python scripts/load_soil.py --site-id cand-sri-lanka --source soilgrids
```

Open the notebook in VS Code and choose the `backend/.venv` interpreter. To execute headless:

```bash
uv run python -m ipykernel install --sys-prefix --name ftm-backend   # once
uv run python -m nbconvert --to notebook --execute --inplace ../notebooks/01_weather_eda.ipynb
```

Outputs are committed so the notebook reads without running it. Re-execute after the data changes.

"""DEMO harness for the engine: synthetic weather and illustrative strategies. Owner: M4.

Everything here is DEMO and labelled as such:

- ``DEMO_FORCING_SOURCE`` (``demo-synthetic-forcing``) is deterministic synthetic weather produced by
  ``synthetic_forcing``. It is NOT the ``demo-weather`` source of ``data/fixtures/demo.json`` and it never
  feeds the fake ``results`` there; the engine computes its own results from it.
- ``DEMO_ELEVATION_M`` belongs to the synthetic weather scenario, not to a surveyed site.
- ``demo_strategies`` are ILLUSTRATIVE rotations (D5 is open); crops come from the cited FAO-56 catalog.
- The soil is the DEMO FAO-56 Table 19 assumption (``params.demo_soil``) until M3 delivers site soil (D8).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ftm.contracts.models import QualityFlag, SeasonPlan, Site, Source, Strategy, ValueKind
from ftm.engine.forcing import EXPECTED_UNITS, RAIN, RH, RS, TDEW, TMAX, TMIN, WIND, flag_col
from ftm.engine.rotation import SUPPORTED_IRRIGATION_RULE

DEMO_FORCING_ID = "demo-synthetic-forcing"
DEMO_FORCING_RUN_ID = "demo-synthetic-forcing-v1"
DEMO_FORCING_SEED = 20261114
DEMO_ELEVATION_M = 800.0
DEMO_ELEVATION_NOTE = "800 m, DEMO value paired with synthetic weather (not a surveyed site elevation)"
DEMO_MISSING_RAIN_DAY = pd.Timestamp("2004-07-10")  # shows the season-block exclusion rule
DEMO_HORIZON = (date(2027, 1, 1), date(2028, 12, 31))
VARIABLES = (RAIN, TMAX, TMIN, TDEW, RH, WIND, RS)

DEMO_FORCING_SOURCE = Source(
    id=DEMO_FORCING_ID,
    provider="DEMO (Farm Time Machine engine)",
    product="Deterministic synthetic daily weather for engine demonstration",
    version="v1",
    variables=list(VARIABLES),
    units={v: EXPECTED_UNITS[v] for v in VARIABLES},
    kind=ValueKind.DEMO,
    temporal_resolution="daily",
    limitations=(
        "Not real weather. Seeded random series with a seasonal cycle, generated in code "
        "(ftm.engine.demo.synthetic_forcing). Use only to exercise the engine."
    ),
    is_demo=True,
)


def synthetic_forcing(
    start: str = "1990-01-01", end: str = "2014-12-31", seed: int = DEMO_FORCING_SEED
) -> pd.DataFrame:
    """Deterministic synthetic weather in the engine's wide forcing shape. DEMO only."""
    idx = pd.date_range(start, end, freq="D", name="date")
    rng = np.random.default_rng(seed)
    n = len(idx)
    season = np.sin(2 * np.pi * (idx.day_of_year.to_numpy() - 100) / 365.0)
    tmax = 18 + 13 * season + rng.normal(0, 3, n)
    tmin = tmax - rng.uniform(8, 16, n)
    wet = rng.random(n) < (0.18 + 0.10 * np.clip(season, 0, None))
    df = pd.DataFrame(
        {
            RAIN: np.where(wet, rng.gamma(0.7, 9.0, n), 0.0),
            TMAX: tmax,
            TMIN: tmin,
            TDEW: tmin - rng.uniform(0, 5, n),
            RH: rng.uniform(35, 85, n),
            WIND: rng.uniform(1.5, 6.0, n),
            RS: np.clip(17 + 9 * season + rng.normal(0, 3, n), 2, 32),
        },
        index=idx,
    )
    for v in VARIABLES:
        df[flag_col(v)] = QualityFlag.OK.value
    if idx[0] <= DEMO_MISSING_RAIN_DAY <= idx[-1]:
        df.loc[DEMO_MISSING_RAIN_DAY, RAIN] = np.nan
        df.loc[DEMO_MISSING_RAIN_DAY, flag_col(RAIN)] = QualityFlag.MISSING.value
    df["source_id"] = DEMO_FORCING_ID
    df["processing_run_id"] = DEMO_FORCING_RUN_ID
    return df


def demo_site() -> Site:
    """The DEMO site of ``data/fixtures/demo.json`` (a candidate region, not a chosen site; D1 open)."""
    from ftm.fixtures import load_demo

    return next(s for s in load_demo().sites if s.id == "demo-site")


def _season(crop: str | None, a: date, b: date, irrigated: bool) -> SeasonPlan:
    return SeasonPlan(
        crop_id=crop, plant_date=a, end_date=b, irrigation_rule=SUPPORTED_IRRIGATION_RULE if irrigated else None
    )


def demo_strategies(site_id: str = "demo-site") -> list[Strategy]:
    """ILLUSTRATIVE strategies (D5 open). IDs differ from demo.json so they never mix with its fake results."""
    return [
        Strategy(
            id="engine-demo-baseline",
            site_id=site_id,
            name="DEMO current practice: irrigated maize every year",
            is_baseline=True,
            is_demo=True,
            seasons=[
                _season("maize-grain", date(2027, 4, 20), date(2027, 10, 10), True),
                _season("maize-grain", date(2028, 4, 20), date(2028, 10, 10), True),
            ],
        ),
        Strategy(
            id="engine-demo-alt-a",
            site_id=site_id,
            name="DEMO alternative A: irrigated maize, then rainfed winter wheat",
            is_demo=True,
            seasons=[
                _season("maize-grain", date(2027, 4, 20), date(2027, 10, 10), True),
                _season("winter-wheat", date(2027, 10, 15), date(2028, 9, 15), False),
            ],
        ),
        Strategy(
            id="engine-demo-alt-b",
            site_id=site_id,
            name="DEMO alternative B: rainfed grain sorghum every year",
            is_demo=True,
            seasons=[
                _season("sorghum-grain", date(2027, 5, 25), date(2027, 10, 1), False),
                _season("sorghum-grain", date(2028, 5, 25), date(2028, 10, 1), False),
            ],
        ),
    ]

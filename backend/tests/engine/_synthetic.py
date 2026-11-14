"""TEST-ONLY synthetic inputs for engine tests. These are NOT crop parameters, weather or results."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ftm.contracts.models import CropProfile, ParamValue, QualityFlag, SeasonPlan, SoilProfile, Strategy
from ftm.engine.forcing import RAIN, RH, RS, TDEW, TMAX, TMIN, WIND, flag_col
from ftm.engine.params import CropEntry, SoilSpec
from ftm.engine.rotation import SUPPORTED_IRRIGATION_RULE

TEST_REF = "TEST ONLY: synthetic value, not from any source"
IRR = SUPPORTED_IRRIGATION_RULE


def pv(value: float | None, unit: str) -> ParamValue:
    return ParamValue(value=value, unit=unit, reference=TEST_REF if value is not None else None)


def make_forcing(start: str, end: str, seed: int = 0) -> pd.DataFrame:
    idx = pd.date_range(start, end, freq="D", name="date")
    rng = np.random.default_rng(seed)
    n = len(idx)
    season = np.sin(2 * np.pi * (idx.day_of_year.to_numpy() - 100) / 365.0)
    tmax = 22 + 10 * season + rng.normal(0, 2, n)
    tmin = tmax - rng.uniform(6, 14, n)
    df = pd.DataFrame(
        {
            RAIN: rng.gamma(0.4, 8.0, n) * (rng.random(n) < 0.3),
            TMAX: tmax,
            TMIN: tmin,
            TDEW: tmin - rng.uniform(0, 4, n),
            RH: rng.uniform(35, 85, n),
            WIND: rng.uniform(1, 5, n),
            RS: np.clip(18 + 8 * season + rng.normal(0, 3, n), 2, 32),
        },
        index=idx,
    )
    for v in (RAIN, TMAX, TMIN, TDEW, RH, WIND, RS):
        df[flag_col(v)] = QualityFlag.OK.value
    df["source_id"] = "test-src"
    df["processing_run_id"] = "test-run"
    return df


def crop(
    cid: str = "crop-a",
    *,
    p: float | None = 0.5,
    root: float | None = 0.8,
    height: float | None = 1.0,
    window: tuple[str, str] | None = None,
) -> CropEntry:
    profile = CropProfile(
        id=cid,
        name=f"Synthetic {cid}",
        kc_ini=pv(0.4, "-"),
        kc_mid=pv(1.1, "-"),
        kc_end=pv(0.6, "-"),
        stage_lengths_days={
            "ini": pv(20, "days"),
            "dev": pv(30, "days"),
            "mid": pv(40, "days"),
            "late": pv(20, "days"),
        },
        max_root_depth_m=pv(root, "m"),
        depletion_fraction_p=pv(p, "-"),
        planting_window=window,
    )
    return CropEntry(profile=profile, max_height_m=pv(height, "m"), tr55_cover="row_crops_straight_row_good")


def soil(awc: float | None = 150.0, depth: float = 1.0) -> SoilSpec:
    profile = SoilProfile(
        id="test-soil",
        site_id="test-site",
        available_water_capacity_mm_per_m=pv(awc, "mm/m"),
        root_zone_depth_m=pv(None, "m"),
        source_ids=["test-soil-src"],
    )
    return SoilSpec(profile=profile, data_depth_m=depth, hsg="B", annex7_class="medium")


def strategy(sid: str, seasons: list[tuple[str | None, date, date, str | None]]) -> Strategy:
    return Strategy(
        id=sid,
        site_id="test-site",
        name=sid,
        seasons=[SeasonPlan(crop_id=c, plant_date=a, end_date=b, irrigation_rule=r) for c, a, b, r in seasons],
    )

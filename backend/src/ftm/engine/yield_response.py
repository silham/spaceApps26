"""Water-limited relative yield (FAO-33 / FAO-56 Table 24). Owner: M4.

Doorenbos & Kassam (1979), FAO Irrigation and Drainage Paper 33, eq. 1 (seasonal form, also the basis of
FAO-56 Table 24)::

    1 - Ya/Ym = Ky * (1 - ETa/ETm)

``ETm`` is the unstressed crop evapotranspiration (the model's ETc = Kc * ET0) and ``ETa`` the actual
evapotranspiration (the model's AET), both summed over the crop days of one season. The result is the yield
as a share of the water-unlimited yield. It cannot give tonnes per hectare on its own: that needs the
farmer's own usual yield, which is a user input and never a prediction. Nutrients, pests, heat or frost and
variety are not modelled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ftm.contracts.models import SeasonPlan, Strategy
from ftm.engine.params import CropEntry

REL_YIELD_PREFIX = "relative_yield_pct__s"
YIELD_T_HA_PREFIX = "yield_t_ha__s"


def relative_yield(ky: float, aet_mm: float, etc_mm: float) -> float:
    """FAO-33 eq. 1, clamped to [0, 1]. No water demand (ETm = 0) means no deficit."""
    if etc_mm <= 0:
        return 1.0
    return float(min(1.0, max(0.0, 1.0 - ky * (1.0 - aet_mm / etc_mm))))


def ordered_seasons(strategy: Strategy) -> list[SeasonPlan]:
    """Seasons in the order ``daily_schedule`` numbers them (by planting date)."""
    return sorted(strategy.seasons, key=lambda s: s.plant_date)


def yield_metrics(trace: pd.DataFrame, strategy: Strategy, crops: dict[str, CropEntry] | object) -> dict[str, float]:
    """Per-season ``relative_yield_pct__s<k>`` (and ``yield_t_ha__s<k>`` when the farmer gave a usual yield).

    A season whose crop has no Ky gets no metric: the claim is blocked, not guessed.
    """
    out: dict[str, float] = {}
    season_id = trace["season_id"].to_numpy()
    aet, etc = trace["aet_mm"].to_numpy(dtype="float64"), trace["etc_mm"].to_numpy(dtype="float64")
    for k, season in enumerate(ordered_seasons(strategy)):
        if season.crop_id is None:
            continue
        entry = crops[season.crop_id]  # type: ignore[index]
        ky = entry.profile.ky_season
        if ky is None or ky.value is None:
            continue
        mask = season_id == k
        if not mask.any():
            continue
        rel = relative_yield(float(ky.value), float(np.nansum(aet[mask])), float(np.nansum(etc[mask])))
        out[f"{REL_YIELD_PREFIX}{k}"] = 100.0 * rel
        if season.usual_yield_t_ha is not None:
            out[f"{YIELD_T_HA_PREFIX}{k}"] = rel * season.usual_yield_t_ha
    return out


def parse_yield_metric(metric: str) -> tuple[str, int] | None:
    """('relative_yield_pct' | 'yield_t_ha', season index) for a per-season metric name, else None."""
    for prefix in (REL_YIELD_PREFIX, YIELD_T_HA_PREFIX):
        if metric.startswith(prefix):
            return prefix[: -len("__s")], int(metric[len(prefix) :])
    return None

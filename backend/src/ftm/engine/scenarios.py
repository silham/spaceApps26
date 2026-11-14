"""ks-field-2 strategies (D5, docs/decisions.md). Owner: M4.

Site evidence (M3, remote only): USDA CDL shows corn alternating with winter wheat 2008-2024, with a
double-crop sorghum after wheat in 2011 and 2013. Horizon: two agricultural years, so one corn and one
wheat season fit; every strategy runs on the same paired weather.

- Baseline "current practice": irrigated corn, then irrigated winter wheat (fallow in between).
- Alternative A "add double-crop sorghum": baseline + rainfed grain sorghum straight after wheat harvest.
  More cover and crops, more water use. Trade-off: soil protection vs water.
- Alternative B "rainfed sorghum instead of corn": rainfed grain sorghum, then irrigated winter wheat.
  Only the summer crop and its irrigation change. Trade-off: water vs crop choice.

Planting dates come from the FAO-56 Table 11 footnote 2 temperature rules applied to the site's own
weather over the sample pool (``engine.calendar``); grain sorghum has no such rule, so its main-season date
(1 June, inside the "May/June" planting period of FAO-56 Table 11's USA sorghum row) is an M4 scenario
choice. A season ends when the crop reaches maturity (sum of its stage lengths). A crop with missing stage
lengths (Kansas wheat until the NASS season length is entered, D4) makes its strategy infeasible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import pandas as pd

from ftm.contracts.models import SeasonPlan, Strategy
from ftm.engine.calendar import PlantingDate, planting_date
from ftm.engine.params import CropEntry, load_crops, load_local_crops
from ftm.engine.rotation import SUPPORTED_IRRIGATION_RULE, missing_parameters, stage_lengths

SCENARIO_HORIZON = (date(2027, 1, 1), date(2028, 12, 31))
SORGHUM_MAIN_SEASON_MD = "06-01"  # M4 choice inside FAO-56 Table 11 "May/June" (USA row); no FAO-56 rule
DOUBLE_CROP_GAP_DAYS = 1  # sorghum planted the day after wheat harvest (M4 scenario choice, no-till assumed)
WheatChoice = Literal["kansas-local", "fao56-idaho"]
WHEAT_IDS: dict[WheatChoice, str] = {"kansas-local": "winter-wheat-ks", "fao56-idaho": "winter-wheat"}


@dataclass(frozen=True)
class Scenario:
    crops: dict[str, CropEntry]
    strategies: list[Strategy]
    planting: dict[str, PlantingDate]
    notes: tuple[str, ...]


def _end(entry: CropEntry, plant: date) -> date | None:
    """Maturity date (plant + stage sum), or None while a stage length is missing (blocks the season)."""
    if any(m.startswith("stage_lengths_days") for m in missing_parameters(entry)):
        return None
    return plant + timedelta(days=sum(stage_lengths(entry)))


def _season(crop: CropEntry, plant: date, irrigated: bool, placeholder_end: date) -> SeasonPlan:
    end = _end(crop, plant)
    return SeasonPlan(
        crop_id=crop.profile.id,
        plant_date=plant,
        end_date=end or placeholder_end,
        irrigation_rule=SUPPORTED_IRRIGATION_RULE if irrigated else None,
    )


def build_ks_field_2(
    forcing: pd.DataFrame, pool_years: list[int], *, site_id: str = "ks-field-2", wheat: WheatChoice = "kansas-local"
) -> Scenario:
    crops = {**load_crops(), **load_local_crops()}
    maize, sorghum, wht = crops["maize-grain"], crops["sorghum-grain"], crops[WHEAT_IDS[wheat]]
    p_maize = planting_date(forcing, "maize_spring_13c", pool_years)
    p_wheat = planting_date(forcing, "winter_wheat_fall_17c", pool_years)
    y0 = SCENARIO_HORIZON[0].year
    horizon_end = SCENARIO_HORIZON[1]

    corn = _season(maize, p_maize.on(y0), True, horizon_end)
    wheat_irr = _season(wht, p_wheat.on(y0), True, horizon_end)
    sorghum_main = _season(sorghum, date.fromisoformat(f"{y0}-{SORGHUM_MAIN_SEASON_MD}"), False, horizon_end)
    double = None
    if (wheat_end := _end(wht, wheat_irr.plant_date)) is not None:
        double = _season(sorghum, wheat_end + timedelta(days=DOUBLE_CROP_GAP_DAYS), False, horizon_end)

    notes = [
        f"Maize planting {p_maize.month_day}: {p_maize.reference} "
        f"(years spread {p_maize.spread[0]}-{p_maize.spread[1]}).",
        f"Winter wheat sowing {p_wheat.month_day}: {p_wheat.reference} "
        f"(years spread {p_wheat.spread[0]}-{p_wheat.spread[1]}).",
        f"Grain sorghum main-season planting {SORGHUM_MAIN_SEASON_MD}: M4 scenario choice within the FAO-56 "
        "Table 11 'May/June' planting period (no FAO-56 temperature rule for sorghum).",
        "Seasons end at maturity (sum of the crop's stage lengths); frost and harvest logistics are not modelled.",
    ]
    if wheat == "fao56-idaho":
        notes.append(
            "Winter wheat uses the FAO-56 Table 11 Idaho row as printed (335 d); harvest falls in September, "
            "later than in Kansas, so the double crop after wheat does not fit the horizon."
        )
    if double is None:
        notes.append("Double-crop sorghum date unknown until the wheat harvest is known (Kansas wheat season pending).")

    def strat(sid: str, name: str, seasons: list[SeasonPlan], baseline: bool = False) -> Strategy:
        return Strategy(id=sid, site_id=site_id, name=name, is_baseline=baseline, seasons=seasons)

    alt_a = [corn, wheat_irr, *([double] if double else [])]  # without a wheat harvest the wheat blocks it
    strategies = [
        strat(
            "ks2-current-corn-wheat",
            "Current practice: irrigated corn, then irrigated winter wheat",
            [corn, wheat_irr],
            baseline=True,
        ),
        strat("ks2-alt-a-double-crop", "Alternative A: corn, wheat, then rainfed double-crop sorghum", alt_a),
        strat(
            "ks2-alt-b-sorghum-wheat",
            "Alternative B: rainfed sorghum, then irrigated winter wheat",
            [sorghum_main, wheat_irr],
        ),
    ]
    return Scenario(crops, strategies, {"maize": p_maize, "winter_wheat": p_wheat}, tuple(notes))

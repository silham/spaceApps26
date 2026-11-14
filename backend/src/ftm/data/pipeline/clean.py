"""Pipeline step: clean (Data Journey stage "Clean"). Owner: M3.

Checks units, rejects physically impossible values and flags internally inconsistent ones.
Values are rejected (not clipped) per DEVELOPMENT_GUIDE.md section 6; ``raw_value`` is never touched.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ftm.contracts.models import ProcessingStep, QualityFlag


@dataclass(frozen=True)
class VariableRule:
    unit: str
    min_value: float
    max_value: float
    basis: str


# Loose physical-plausibility limits, NOT climatology. They only catch impossible values.
# Temperature/rain extremes: WMO Weather & Climate Extremes Archive, https://wmo.asu.edu/
# Shortwave limit: daily surface insolation cannot exceed top-of-atmosphere Ra, which peaks near
# ~45 MJ/m2/day at polar midsummer (FAO-56 eq. 21 / Annex 2 Table 2.6).
RULES: dict[str, VariableRule] = {
    "T2M_MAX": VariableRule("C", -90.0, 60.0, "beyond WMO-recorded air-temperature extremes"),
    "T2M_MIN": VariableRule("C", -90.0, 60.0, "beyond WMO-recorded air-temperature extremes"),
    "T2M": VariableRule("C", -90.0, 60.0, "beyond WMO-recorded air-temperature extremes"),
    "T2MDEW": VariableRule("C", -90.0, 60.0, "dew point beyond WMO-recorded air-temperature extremes"),
    "PRECTOTCORR": VariableRule("mm/day", 0.0, 2000.0, "negative or beyond WMO 24-h rainfall record"),
    "RH2M": VariableRule("%", 0.0, 100.0, "relative humidity outside 0-100%"),
    "WS2M": VariableRule("m/s", 0.0, 75.0, "negative or implausible daily-mean 2 m wind"),
    "ALLSKY_SFC_SW_DWN": VariableRule("MJ/m^2/day", 0.0, 50.0, "negative or above top-of-atmosphere max"),
}


class UnitMismatchError(ValueError):
    """A variable arrived in a unit we have no declared conversion for. Fail loudly, never guess."""


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, ProcessingStep]:
    out = df.copy()
    ok = out["quality_flag"] == QualityFlag.OK.value

    # 1. Units: POWER AG already delivers FAO-56 units, so no conversion is applied; mismatches stop the run.
    for var, unit in out.drop_duplicates("variable").set_index("variable")["unit"].items():
        rule = RULES.get(str(var))
        if rule is not None and unit != rule.unit:
            raise UnitMismatchError(f"{var}: got unit {unit!r}, expected {rule.unit!r}")

    # 2. Physical bounds -> rejected (value removed from processed series, raw kept).
    rejected_per_var: dict[str, int] = {}
    for var, rule in RULES.items():
        mask = ok & (out["variable"] == var)
        vals = out.loc[mask, "processed_value"]
        bad = vals[(vals < rule.min_value) | (vals > rule.max_value)].index
        if len(bad):
            out.loc[bad, ["processed_value", "quality_flag", "flag_reason"]] = [
                np.nan,
                QualityFlag.REJECTED.value,
                f"{rule.basis} [{rule.min_value}, {rule.max_value}] {rule.unit}",
            ]
            rejected_per_var[var] = len(bad)

    # 3. Consistency: Tmin > Tmax on the same day -> both flagged (kept; we cannot tell which is wrong).
    inconsistent_days = _flag_tmin_above_tmax(out)

    unknown = sorted(set(out["variable"]) - set(RULES))
    step = ProcessingStep(
        name="clean",
        params={
            "bounds": {v: [r.min_value, r.max_value, r.unit] for v, r in RULES.items()},
            "unit_conversions": "none (source units match model units)",
            "variables_without_rules": unknown,
            "rejected_per_variable": rejected_per_var,
            "tmin_above_tmax_days": inconsistent_days,
        },
        affected_count=sum(rejected_per_var.values()) + 2 * inconsistent_days,
        reason=(
            "Rejected physically impossible values (not clipped) and flagged days where minimum "
            "temperature exceeds maximum. Units verified against the model's expected units."
        ),
    )
    return out, step


def _flag_tmin_above_tmax(out: pd.DataFrame) -> int:
    ok = out["quality_flag"] == QualityFlag.OK.value
    tmax = out[ok & (out["variable"] == "T2M_MAX")].set_index("date")["processed_value"]
    tmin = out[ok & (out["variable"] == "T2M_MIN")].set_index("date")["processed_value"]
    both = tmax.index.intersection(tmin.index)
    bad_dates = set(both[(tmin.loc[both] > tmax.loc[both]).to_numpy()])
    if not bad_dates:
        return 0
    mask = ok & out["variable"].isin(["T2M_MAX", "T2M_MIN"]) & out["date"].isin(bad_dates)
    out.loc[mask, ["quality_flag", "flag_reason"]] = [QualityFlag.FLAGGED.value, "T2M_MIN > T2M_MAX"]
    return len(bad_dates)

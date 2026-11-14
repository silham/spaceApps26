"""Engine-side check of the daily forcing frame. Owner: M4.

Wide shape proposed to M3 on PR #2 (``ftm.data.forcing.get_daily_forcing``):

- index: ``DatetimeIndex`` named ``date``, daily, sorted, unique, complete (absent day = NaN row)
- ``<VAR>``: float processed value, NaN if missing / rejected / unresolved
- ``<VAR>__flag``: ``QualityFlag`` value
- ``source_id``, ``processing_run_id``: one constant value each (AGENTS.md rule 2)

Missing rainfall is never zero (DEVELOPMENT_GUIDE.md section 6): nothing here fills or drops NaN.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ftm.contracts.models import QualityFlag

RAIN = "PRECTOTCORR"
TMAX = "T2M_MAX"
TMIN = "T2M_MIN"
TDEW = "T2MDEW"
RH = "RH2M"
WIND = "WS2M"
RS = "ALLSKY_SFC_SW_DWN"

REQUIRED_VARIABLES: tuple[str, ...] = (RAIN, TMAX, TMIN, RS, WIND)
OPTIONAL_VARIABLES: tuple[str, ...] = (TDEW, RH)  # at least one is needed for Penman-Monteith humidity
EXPECTED_UNITS: dict[str, str] = {
    RAIN: "mm/day",
    TMAX: "C",
    TMIN: "C",
    TDEW: "C",
    RH: "%",
    WIND: "m/s",
    RS: "MJ/m^2/day",
}
# FLAGGED (e.g. Tmin > Tmax) is not usable: we cannot tell which value is wrong, so it is not repaired.
USABLE_FLAGS = frozenset({QualityFlag.OK.value, QualityFlag.ESTIMATED.value})


class ForcingContractError(ValueError):
    """The forcing frame does not have the agreed shape. Fail loudly; never reshape silently."""


class ForcingGapError(ValueError):
    """A NaN reached a computation that cannot accept it. Missing rain is never treated as 0 mm."""


@dataclass(frozen=True)
class ForcingInfo:
    source_id: str
    processing_run_id: str
    start: pd.Timestamp
    end: pd.Timestamp
    n_days: int


def flag_col(variable: str) -> str:
    return f"{variable}__flag"


def assert_forcing_contract(df: pd.DataFrame) -> ForcingInfo:
    """Validate the wide forcing frame and return its provenance. Raises ``ForcingContractError``."""
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.name != "date":
        raise ForcingContractError("index must be a DatetimeIndex named 'date'")
    if df.empty:
        raise ForcingContractError("forcing frame is empty")
    if not df.index.is_monotonic_increasing or not df.index.is_unique:
        raise ForcingContractError("dates must be sorted and unique (drop DUPLICATE rows before the pivot)")
    expected = pd.date_range(df.index[0], df.index[-1], freq="D", name="date")
    if len(expected) != len(df.index) or not (expected == df.index).all():
        raise ForcingContractError("dates must be complete; an absent day is a NaN row, never a dropped row")

    missing = [c for v in REQUIRED_VARIABLES for c in (v, flag_col(v)) if c not in df.columns]
    if missing:
        raise ForcingContractError(f"missing columns: {missing}")
    if not any(v in df.columns and flag_col(v) in df.columns for v in OPTIONAL_VARIABLES):
        raise ForcingContractError(f"need at least one humidity variable with flags: {list(OPTIONAL_VARIABLES)}")

    valid_flags = {f.value for f in QualityFlag}
    for v in (*REQUIRED_VARIABLES, *OPTIONAL_VARIABLES):
        if v not in df.columns:
            continue
        if not pd.api.types.is_float_dtype(df[v]):
            raise ForcingContractError(f"{v} must be float (NaN for missing), got {df[v].dtype}")
        bad = set(df[flag_col(v)].dropna().unique()) - valid_flags
        if bad or df[flag_col(v)].isna().any():
            raise ForcingContractError(f"{flag_col(v)} has unknown or empty flags: {sorted(map(str, bad))}")
        # A usable flag must carry a value; a NaN value must not claim to be usable.
        if (df[flag_col(v)].isin(USABLE_FLAGS) & df[v].isna()).any():
            raise ForcingContractError(f"{v}: NaN value with a usable flag")

    ids = {}
    for col in ("source_id", "processing_run_id"):
        if col not in df.columns:
            raise ForcingContractError(f"missing column {col!r}")
        values = df[col].dropna().unique()
        if len(values) != 1:
            # Exactly one weather source per run: two rainfall sources are never summed (guide section 6).
            raise ForcingContractError(f"{col} must have exactly one value, got {len(values)}")
        ids[col] = str(values[0])

    return ForcingInfo(
        source_id=ids["source_id"],
        processing_run_id=ids["processing_run_id"],
        start=df.index[0],
        end=df.index[-1],
        n_days=len(df),
    )


def usable(df: pd.DataFrame, variable: str) -> pd.Series:
    """Boolean mask: value present and flagged OK or ESTIMATED. Absent variable -> all False."""
    if variable not in df.columns:
        return pd.Series(False, index=df.index)
    return df[flag_col(variable)].isin(USABLE_FLAGS) & df[variable].notna()


def usable_values(df: pd.DataFrame, variable: str) -> np.ndarray:
    """Values with unusable days set to NaN (so FLAGGED values are not used)."""
    if variable not in df.columns:
        return np.full(len(df), np.nan)
    return np.asarray(df[variable].where(usable(df, variable)), dtype="float64")

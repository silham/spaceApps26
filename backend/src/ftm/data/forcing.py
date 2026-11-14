"""Engine-facing accessor for processed daily forcing. Owner: M3, consumed by M4."""

from datetime import date

import pandas as pd


def get_daily_forcing(site_id: str, start: date, end: date, weather_source_id: str) -> pd.DataFrame:
    """Return one row per day with processed variables, quality flags and source IDs.

    Exactly one weather/rainfall source per run. Missing values stay NaN with a flag; never 0.
    TODO(M3): read from the observation table for the latest ProcessingRun.
    """
    raise NotImplementedError("M3: implement forcing accessor")

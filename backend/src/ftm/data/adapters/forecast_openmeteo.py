"""ECMWF SEAS5 seasonal forecast through the Open-Meteo Seasonal Forecast API. Owner: M3. D16.

Two point requests are stored unchanged as raw snapshots:

* daily ``precipitation_sum``, ``temperature_2m_max`` and ``temperature_2m_min`` for the control run and
  ``member01``..``member50`` (51 members, 36 km);
* monthly ``precipitation_anomaly`` and ``temperature_2m_anomaly``: the ensemble-mean anomaly against the
  model's own hindcast climatology (Open-Meteo docs: "Anomaly = Forecast - Model Climatology").

The forecast is NOT used as weather in the water balance. It only sets the odds of below / near / above
normal months, which weight the NASA POWER years drawn for the coming months (D16). Open-Meteo states the
data are not bias-corrected and should be read as area forecasts.

Docs: https://open-meteo.com/en/docs/seasonal-forecast-api. Data licence CC BY 4.0; the free API is for
non-commercial use; attribution with a link is required wherever the data are shown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd

from ftm.config import get_settings
from ftm.contracts.models import Source, ValueKind
from ftm.data.raw_cache import RawSnapshot, find_latest_raw, save_raw
from ftm.provenance import sha256_file

SEASONAL_URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
SOURCE_KEY = "openmeteo_seas5"
DAILY_VARS = ("precipitation_sum", "temperature_2m_max", "temperature_2m_min")
MONTHLY_VARS = ("precipitation_anomaly", "temperature_2m_anomaly")
MAX_FORECAST_DAYS = 217  # the API refuses more ("Allowed range 0 to 217"), checked 2026-11-15
NATIVE_RESOLUTION = "36 km (ECMWF SEAS5)"
ATTRIBUTION = "Weather data by Open-Meteo.com (https://open-meteo.com/), ECMWF SEAS5 seasonal forecast, CC BY 4.0"
LICENSE = "CC BY 4.0 (data); Open-Meteo free API for non-commercial use"


class ForecastResponseError(ValueError):
    """The response does not hold the expected variables (names are checked, never assumed)."""


@dataclass(frozen=True)
class SeasonalForecast:
    """Parsed members. ``daily[var]`` is a (days x members) frame indexed by date; values stay as delivered."""

    daily: dict[str, pd.DataFrame]
    monthly_anomaly: pd.DataFrame  # index: first day of month; columns: precipitation_mm, temperature_k
    units: dict[str, str]
    grid_latitude: float | None
    grid_longitude: float | None

    @property
    def n_members(self) -> int:
        return int(self.daily["precipitation_sum"].shape[1])


def _params(lat: float, lon: float) -> list[tuple[str, str]]:
    return [("latitude", f"{lat:.4f}"), ("longitude", f"{lon:.4f}"), ("timezone", "GMT")]


def daily_params(lat: float, lon: float, start: date, end: date) -> list[tuple[str, str]]:
    return [
        *_params(lat, lon),
        ("daily", ",".join(DAILY_VARS)),
        ("start_date", start.isoformat()),
        ("end_date", end.isoformat()),
    ]


def monthly_params(lat: float, lon: float) -> list[tuple[str, str]]:
    return [*_params(lat, lon), ("monthly", ",".join(MONTHLY_VARS))]


def raw_filename(kind: str, lat: float, lon: float, start: date | None = None) -> str:
    tag = f"_{start:%Y%m%d}" if start else ""
    return f"{kind}_{lat:.4f}_{lon:.4f}{tag}.json"


def _get(url: str, params: Any, client: httpx.Client | None, timeout_s: float) -> bytes:
    own = client is None
    http = client or httpx.Client(timeout=timeout_s)
    try:
        r = http.get(url, params=params)
        r.raise_for_status()
    finally:
        if own:
            http.close()
    body = json.loads(r.content)
    if body.get("error"):
        raise ForecastResponseError(str(body.get("reason")))
    return r.content


def fetch_cached(
    lat: float,
    lon: float,
    start: date,
    end: date,
    *,
    raw_dir: Path | None = None,
    client: httpx.Client | None = None,
    timeout_s: float = 60.0,
) -> tuple[RawSnapshot, RawSnapshot]:
    """Daily and monthly raw snapshots, reused when downloaded today (SEAS5 is issued once a month)."""
    root = raw_dir or get_settings().raw_dir
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out = []
    for kind, params in (
        ("daily", daily_params(lat, lon, start, end)),
        ("monthly", monthly_params(lat, lon)),
    ):
        name = raw_filename(kind, lat, lon, start if kind == "daily" else None)
        existing = find_latest_raw(SOURCE_KEY, name, root)
        if existing is not None and existing.parent.name == today:
            retrieved = datetime.strptime(existing.parent.name, "%Y-%m-%d").replace(tzinfo=UTC)
            out.append(
                RawSnapshot(existing, existing.relative_to(root.parent).as_posix(), sha256_file(existing), retrieved)
            )
            continue
        content = _get(SEASONAL_URL, params, client, timeout_s)
        parse_daily(content) if kind == "daily" else parse_monthly(content)  # never cache a malformed body
        out.append(save_raw(SOURCE_KEY, name, content, root))
    return out[0], out[1]


def _members(block: dict[str, Any], var: str) -> pd.DataFrame:
    cols = [var, *sorted(k for k in block if k.startswith(f"{var}_member"))]
    if var not in block or len(cols) < 2:
        raise ForecastResponseError(f"variable {var!r} or its members missing from the response")
    idx = pd.to_datetime(block["time"])
    data = {c: np.asarray([np.nan if v is None else float(v) for v in block[c]], dtype="float64") for c in cols}
    return pd.DataFrame(data, index=idx).rename(columns={var: f"{var}_control"})


def parse_daily(content: bytes) -> dict[str, pd.DataFrame]:
    payload = json.loads(content)
    block = payload.get("daily")
    if not block or "time" not in block:
        raise ForecastResponseError("no daily block in the response")
    return {v: _members(block, v) for v in DAILY_VARS}


def parse_monthly(content: bytes) -> pd.DataFrame:
    payload = json.loads(content)
    block = payload.get("monthly")
    if not block or any(v not in block for v in ("time", *MONTHLY_VARS)):
        raise ForecastResponseError(f"monthly block must hold {MONTHLY_VARS}")
    units = payload.get("monthly_units", {})
    if units.get("precipitation_anomaly") != "mm" or units.get("temperature_2m_anomaly") not in ("K", "°C"):
        raise ForecastResponseError(f"unexpected monthly units {units}")
    idx = pd.to_datetime(block["time"])
    return pd.DataFrame(
        {
            "precipitation_mm": [np.nan if v is None else float(v) for v in block["precipitation_anomaly"]],
            "temperature_k": [np.nan if v is None else float(v) for v in block["temperature_2m_anomaly"]],
        },
        index=idx,
    )


def load(daily: RawSnapshot, monthly: RawSnapshot) -> SeasonalForecast:
    payload = json.loads(daily.path.read_bytes())
    return SeasonalForecast(
        daily=parse_daily(daily.path.read_bytes()),
        monthly_anomaly=parse_monthly(monthly.path.read_bytes()),
        units={k: str(v) for k, v in payload.get("daily_units", {}).items() if "member" not in k},
        grid_latitude=payload.get("latitude"),
        grid_longitude=payload.get("longitude"),
    )


def source_id_for(daily: RawSnapshot, monthly: RawSnapshot) -> str:
    return f"seas5_{daily.sha256[:8]}{monthly.sha256[:8]}"


def build_source(source_id: str, daily: RawSnapshot, monthly: RawSnapshot, fc: SeasonalForecast) -> Source:
    days = fc.daily["precipitation_sum"].index
    return Source(
        id=source_id,
        provider="ECMWF SEAS5 via Open-Meteo",
        product="Open-Meteo Seasonal Forecast API (daily members + monthly anomalies)",
        variables=[*DAILY_VARS, *MONTHLY_VARS],
        units={**fc.units, "precipitation_anomaly": "mm", "temperature_2m_anomaly": "K"},
        kind=ValueKind.FORECAST,
        spatial_resolution=NATIVE_RESOLUTION,
        temporal_resolution="daily (members); monthly (ensemble-mean anomaly)",
        coverage_start=days.min().date() if len(days) else None,
        coverage_end=days.max().date() if len(days) else None,
        retrieved_at=daily.retrieved_at,
        url=SEASONAL_URL,
        doi="10.5194/gmd-12-1087-2019",  # Johnson et al. 2019, SEAS5 system description
        license=LICENSE,
        attribution=ATTRIBUTION,
        qa_notes=(
            f"{fc.n_members} ensemble members. Monthly anomaly = forecast minus the model's own hindcast "
            f"climatology (Open-Meteo). Monthly snapshot: {monthly.relative_path} (sha256 {monthly.sha256})."
        ),
        limitations=(
            "Seasonal forecast odds, not a weather forecast for any day; not bias-corrected; a 36 km area "
            "forecast, not field conditions. Used only to weight historical NASA POWER years (D16)."
        ),
        raw_path=daily.relative_path,
        raw_sha256=daily.sha256,
    )

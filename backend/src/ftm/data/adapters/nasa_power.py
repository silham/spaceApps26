"""NASA POWER daily point API adapter. Owner: M3.

Docs: https://power.larc.nasa.gov/docs/services/api/temporal/daily/

This module only *collects*: it downloads the payload, stores it byte-for-byte as an immutable raw
snapshot, and parses it into a long table whose ``raw_value`` is exactly what POWER delivered (fill
values included). Decoding fill values, QA and gap handling belong to ``ftm.data.pipeline``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
import pandas as pd

from ftm.contracts.models import Source, ValueKind
from ftm.data.raw_cache import RawSnapshot, save_raw

POWER_DAILY_POINT_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
SOURCE_KEY = "power"

# Candidate variable list for the water balance (FAO-56 Penman-Monteith inputs + rainfall).
# To be confirmed with M4; names checked against the response's own "parameters" block at parse time.
DEFAULT_PARAMETERS: tuple[str, ...] = (
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "ALLSKY_SFC_SW_DWN",
    "RH2M",
    "WS2M",
)

# Acknowledgment wording requested by the POWER project (see POWER "Data Access" / referencing page).
ATTRIBUTION = (
    "These data were obtained from the NASA Langley Research Center (LaRC) POWER Project funded "
    "through the NASA Earth Science/Applied Science Program."
)


class PowerResponseError(ValueError):
    """The POWER payload is missing something we rely on (parameter block, fill value, ...)."""


@dataclass(frozen=True)
class PowerDaily:
    """Parsed POWER daily payload. ``observations`` keeps raw values untouched."""

    observations: pd.DataFrame  # columns: date_key, date, variable, unit, raw_value
    units: dict[str, str]
    long_names: dict[str, str]
    fill_value: float
    api_version: str | None
    header_sources: list[str]
    grid_point: tuple[float, float] | None  # (lon, lat) POWER reports for the request
    messages: list[str]


def build_request_params(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    parameters: list[str] | tuple[str, ...],
) -> dict[str, str]:
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError(f"Invalid coordinates: lat={latitude}, lon={longitude}")
    if end < start:
        raise ValueError(f"end ({end}) is before start ({start})")
    if not parameters:
        raise ValueError("At least one POWER parameter is required")
    return {
        "parameters": ",".join(parameters),
        "community": "AG",
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }


def raw_filename(latitude: float, longitude: float, start: date, end: date) -> str:
    return f"daily_point_{latitude:.4f}_{longitude:.4f}_{start:%Y%m%d}_{end:%Y%m%d}.json"


def fetch_daily(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    parameters: list[str] | tuple[str, ...] = DEFAULT_PARAMETERS,
    *,
    client: httpx.Client | None = None,
    raw_dir: Any = None,
    timeout_s: float = 120.0,
) -> RawSnapshot:
    """Download daily POWER data and store the response body unchanged as a raw snapshot.

    Raises ``httpx.HTTPStatusError`` on a non-2xx response; nothing is written in that case.
    The payload is parsed once before saving so a malformed response is never cached as "raw data".
    """
    params = build_request_params(latitude, longitude, start, end, parameters)
    own_client = client is None
    http = client or httpx.Client(timeout=timeout_s)
    try:
        response = http.get(POWER_DAILY_POINT_URL, params=params)
        response.raise_for_status()
    finally:
        if own_client:
            http.close()
    parse_daily(response.content)  # validate structure before caching
    return save_raw(
        SOURCE_KEY,
        raw_filename(latitude, longitude, start, end),
        response.content,
        raw_dir,
    )


def parse_daily(content: bytes) -> PowerDaily:
    """Parse a POWER daily JSON payload into a long table. Values are NOT decoded or cleaned."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise PowerResponseError(f"POWER response is not JSON: {exc}") from exc

    header = payload.get("header") or {}
    if "fill_value" not in header:
        raise PowerResponseError("POWER header has no fill_value; cannot tell missing from real values")
    fill_value = float(header["fill_value"])

    try:
        series: dict[str, dict[str, Any]] = payload["properties"]["parameter"]
    except (KeyError, TypeError) as exc:
        raise PowerResponseError("POWER response has no properties.parameter block") from exc

    meta: dict[str, dict[str, Any]] = payload.get("parameters") or {}
    units = {name: str(meta.get(name, {}).get("units", "unknown")) for name in series}
    long_names = {name: str(meta.get(name, {}).get("longname", name)) for name in series}

    rows = [
        {
            "date_key": key,  # original timestamp string, preserved (guide section 6)
            "date": datetime.strptime(key, "%Y%m%d").date(),
            "variable": name,
            "unit": units[name],
            "raw_value": None if value is None else float(value),
        }
        for name, values in series.items()
        for key, value in values.items()
    ]
    observations = pd.DataFrame(rows, columns=["date_key", "date", "variable", "unit", "raw_value"])

    coords = (payload.get("geometry") or {}).get("coordinates")
    grid_point = (float(coords[0]), float(coords[1])) if coords and len(coords) >= 2 else None
    api = header.get("api") or {}

    return PowerDaily(
        observations=observations,
        units=units,
        long_names=long_names,
        fill_value=fill_value,
        api_version=api.get("version"),
        header_sources=[str(s) for s in header.get("sources", [])],
        grid_point=grid_point,
        messages=[str(m) for m in payload.get("messages", [])],
    )


def build_source(source_id: str, snapshot: RawSnapshot, parsed: PowerDaily) -> Source:
    """Source-register entry for one POWER download (AGENTS.md rule 2)."""
    dates = parsed.observations["date"]
    return Source(
        id=source_id,
        provider="NASA Langley Research Center POWER Project",
        product="POWER Daily API (point, AG community)",
        version=parsed.api_version,
        variables=sorted(parsed.units),
        units=parsed.units,
        kind=ValueKind.REANALYSIS,
        # Native grids differ by variable (meteorology vs solar); recorded per POWER docs, not resampled.
        spatial_resolution="Meteorology ~0.5° x 0.625° (MERRA-2); solar ~1° x 1° (CERES) — per POWER docs",
        temporal_resolution="daily",
        coverage_start=dates.min() if not dates.empty else None,
        coverage_end=dates.max() if not dates.empty else None,
        retrieved_at=snapshot.retrieved_at,
        url=POWER_DAILY_POINT_URL,
        license="NASA open data; acknowledgment requested",
        attribution=ATTRIBUTION,
        qa_notes=(
            f"Fill value {parsed.fill_value} marks missing data; decoded in the QA step. "
            f"Upstream sources: {', '.join(parsed.header_sources) or 'not listed'}."
        ),
        limitations=(
            "Gridded reanalysis/satellite-derived values, not field measurements; a grid cell is much "
            "larger than a farm field."
        ),
        raw_path=snapshot.relative_path,
        raw_sha256=snapshot.sha256,
    )

"""USDA NASS Crop Progress via the Quick Stats API (reference dates for phenology evaluation). Owner: M3/M5.

API: https://quickstats.nass.usda.gov/api  (free key in .env as NASS_API_KEY; never stored in raw files)
Source: USDA National Agricultural Statistics Service, Crop Progress (weekly, state level). Public domain.

The raw file is the API's JSON response body unchanged. The request (without the key) is in the filename.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from ftm.config import get_settings
from ftm.contracts.models import Source, ValueKind
from ftm.data.raw_cache import RawSnapshot, find_latest_raw, save_raw
from ftm.provenance import sha256_file

API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
SOURCE_KEY = "nass"
CITATION = "USDA National Agricultural Statistics Service, Crop Progress (Quick Stats database)."


class NassError(ValueError):
    """The API answer is an error or has no rows for the request."""


def raw_filename(commodity: str, unit: str, state: str, y0: int, y1: int) -> str:
    slug = unit.lower().replace(" ", "_")
    return f"progress_{commodity.lower()}_{slug}_{state.lower()}_{y0}_{y1}.json"


def fetch_progress_cached(
    commodity: str,
    unit: str,
    *,
    state: str = "KS",
    years: range,
    raw_dir: Any = None,
    client: httpx.Client | None = None,
) -> RawSnapshot:
    """Weekly state-level progress (e.g. commodity='CORN', unit='PCT PLANTED'), cached raw."""
    root = raw_dir or get_settings().raw_dir
    name = raw_filename(commodity, unit, state, years.start, years.stop - 1)
    existing = find_latest_raw(SOURCE_KEY, name, root)
    if existing is not None:
        retrieved = datetime.strptime(existing.parent.name, "%Y-%m-%d").replace(tzinfo=UTC)
        return RawSnapshot(existing, existing.relative_to(root.parent).as_posix(), sha256_file(existing), retrieved)
    key = get_settings().nass_api_key
    if not key:
        raise NassError("NASS_API_KEY is not set in .env")
    params = {
        "key": key,
        "source_desc": "SURVEY",
        "commodity_desc": commodity,
        "statisticcat_desc": "PROGRESS",
        "unit_desc": unit,
        "agg_level_desc": "STATE",
        "state_alpha": state,
        "year__GE": str(years.start),
        "year__LE": str(years.stop - 1),
        "format": "JSON",
    }
    own = client is None
    http = client or httpx.Client(timeout=90, transport=httpx.HTTPTransport(retries=3))
    try:
        resp = http.get(API_URL, params=params)
        resp.raise_for_status()
    finally:
        if own:
            http.close()
    parse(resp.content)
    return save_raw(SOURCE_KEY, name, resp.content, root)


def parse(content: bytes) -> pd.DataFrame:
    """Return ``year, week_ending, pct, short_desc`` sorted by date; one row per weekly report."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise NassError(f"NASS response is not JSON: {exc}") from exc
    if "error" in payload:
        raise NassError(f"NASS API error: {payload['error']}")
    rows = payload.get("data") or []
    if not rows:
        raise NassError("NASS returned no rows for this request")
    df = pd.DataFrame(
        {
            "year": [int(r["year"]) for r in rows],
            "week_ending": [date.fromisoformat(r["week_ending"]) for r in rows],
            "pct": [float(str(r["Value"]).replace(",", "")) for r in rows],
            "short_desc": [r["short_desc"] for r in rows],
        }
    )
    return df.sort_values("week_ending").reset_index(drop=True)


def date_at_pct(progress: pd.DataFrame, year: int, pct: float = 50.0) -> date | None:
    """Date the cumulative progress first reaches ``pct``, linearly interpolated between weekly reports.

    None if that year's reports never reach ``pct`` or start above it (no bracketing pair).
    """
    y = progress[progress.year == year].sort_values("week_ending")
    prev = None
    for row in y.itertuples():
        if row.pct >= pct:
            if prev is None:
                return None  # first report already above threshold: date not bracketed
            frac = (pct - prev.pct) / (row.pct - prev.pct) if row.pct != prev.pct else 0.0
            days = (row.week_ending - prev.week_ending).days
            return prev.week_ending + timedelta(days=round(frac * days))
        prev = row
    return None


def build_source(snapshots: list[RawSnapshot], progress: pd.DataFrame) -> Source:
    first = snapshots[0]
    return Source(
        id=f"nass_{first.sha256[:16]}",
        provider="USDA National Agricultural Statistics Service",
        product="Crop Progress, Quick Stats API (state level)",
        version=None,
        variables=sorted(set(progress["short_desc"])),
        units={"progress": "% of state acreage"},
        kind=ValueKind.LITERATURE,
        spatial_resolution="state (Kansas)",
        temporal_resolution="weekly",
        coverage_start=progress["week_ending"].min(),
        coverage_end=progress["week_ending"].max(),
        retrieved_at=first.retrieved_at,
        url=API_URL,
        license="US public domain",
        attribution=CITATION,
        qa_notes="Weekly survey estimates; 50 % date interpolated linearly between reports.",
        limitations=(
            "Statewide progress, not this field's planting date: one field can plant weeks before or after the "
            "state median. Western Kansas often plants on a different schedule from the state as a whole."
        ),
        raw_path=";".join(s.relative_path for s in snapshots)[:4000],
        raw_sha256=first.sha256,
    )

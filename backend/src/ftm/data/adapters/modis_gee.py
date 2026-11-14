"""MODIS MOD13Q1 v061 vegetation indices (NDVI, EVI) via Google Earth Engine. Owner: M3.

Catalog: https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1
Citation: Didan, K. (2021). MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061.
NASA EOSDIS Land Processes DAAC. doi:10.5067/MODIS/MOD13Q1.061

Product facts used here (MOD13 user guide, collection 6.1):
- NDVI/EVI are int16 scaled by 10000; valid range -2000..10000; fill value -3000.
- SummaryQA: 0 good, 1 marginal (useful, check other QA), 2 snow/ice, 3 cloudy.
- DetailedQA (bit fields): 0-1 VI quality, 2-5 usefulness, 6-7 aerosol, 8 adjacent cloud,
  9 BRDF correction, 10 mixed clouds, 11-13 land/water, 14 possible snow/ice, 15 possible shadow.
- Each pixel also carries DayOfYear: the day the chosen observation was acquired within the composite.

Nothing is deleted: snow/ice and cloudy values are kept and flagged, and ``qa_pass`` marks the
good/marginal values that season detection may use (validation plan section 2).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ftm.config import get_settings
from ftm.contracts.models import ProcessingStep, QualityFlag, Source, ValueKind
from ftm.data.raw_cache import RawSnapshot, find_latest_raw, save_raw
from ftm.provenance import sha256_file

COLLECTION = "MODIS/061/MOD13Q1"
SOURCE_KEY = "modis"
BANDS = ("NDVI", "EVI", "SummaryQA", "DetailedQA", "DayOfYear")
VI_BANDS = ("NDVI", "EVI")
SCALE_FACTOR = 0.0001
FILL_VALUE = -3000
VALID_RANGE = (-2000, 10000)
NATIVE_SCALE_M = 231.656358263958  # MODIS sinusoidal 250 m-class pixel size
DOI = "10.5067/MODIS/MOD13Q1.061"
CITATION = (
    "Didan, K. (2021). MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061. "
    "NASA EOSDIS Land Processes DAAC. doi:10.5067/MODIS/MOD13Q1.061"
)
SUMMARY_QA = {0: "good", 1: "marginal", 2: "snow/ice", 3: "cloudy"}
QA_PASS = frozenset({0, 1})

RegionFn = Callable[[float, float, date, date], list[list[Any]]]


class ModisError(ValueError):
    """The Earth Engine answer is empty or not in the expected getRegion shape."""


# --------------------------------------------------------------------------- fetch


def _ee_region(lat: float, lon: float, start: date, end: date) -> list[list[Any]]:
    """One row per composite for the pixel containing the point (Earth Engine ``getRegion``)."""
    import ee  # imported lazily: tests and non-EE code paths do not need credentials

    project = get_settings().ee_project
    if not project:
        raise ModisError("EE_PROJECT is not set (add it to .env); see docs/data-sources.md access check")
    ee.Initialize(project=project)
    col = ee.ImageCollection(COLLECTION).filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
    region: list[list[Any]] = col.select(list(BANDS)).getRegion(ee.Geometry.Point([lon, lat]), NATIVE_SCALE_M).getInfo()
    return region


def raw_filename(lat: float, lon: float, start: date, end: date) -> str:
    return f"mod13q1_point_{lat:.5f}_{lon:.5f}_{start:%Y%m%d}_{end:%Y%m%d}.json"


def fetch_cached(
    lat: float,
    lon: float,
    start: date,
    end: date,
    *,
    raw_dir: Any = None,
    region_fn: RegionFn | None = None,
) -> RawSnapshot:
    """Reuse the newest raw extraction for this request, else query Earth Engine and store it.

    The stored file holds the request and Earth Engine's ``getRegion`` result exactly as returned.
    """
    root = raw_dir or get_settings().raw_dir
    name = raw_filename(lat, lon, start, end)
    existing = find_latest_raw(SOURCE_KEY, name, root)
    if existing is not None:
        retrieved = datetime.strptime(existing.parent.name, "%Y-%m-%d").replace(tzinfo=UTC)
        return RawSnapshot(existing, existing.relative_to(root.parent).as_posix(), sha256_file(existing), retrieved)
    region = (region_fn or _ee_region)(lat, lon, start, end)
    payload = {
        "request": {
            "collection": COLLECTION,
            "bands": list(BANDS),
            "point_lon_lat": [lon, lat],
            "scale_m": NATIVE_SCALE_M,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "method": "ee.ImageCollection.getRegion",
        },
        "result": region,
    }
    content = json.dumps(payload).encode()
    parse(content)  # never cache something we cannot read
    return save_raw(SOURCE_KEY, name, content, root)


# --------------------------------------------------------------------------- parse


@dataclass(frozen=True)
class ModisRaw:
    observations: pd.DataFrame  # long: date_key, date, variable, unit, raw_value
    pixel_center_lon_lat: tuple[float, float] | None
    request: dict[str, Any]


def parse(content: bytes) -> ModisRaw:
    try:
        payload = json.loads(content)
        header, *rows = payload["result"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ModisError(f"unexpected MODIS extraction file: {exc}") from exc
    if not rows:
        raise ModisError("Earth Engine returned no composites for this point and period")
    missing = [b for b in BANDS if b not in header]
    if missing:
        raise ModisError(f"getRegion result lacks bands {missing}")
    idx = {name: i for i, name in enumerate(header)}
    records = []
    for r in rows:
        image_id = str(r[idx["id"]])  # e.g. "2024_01_01" = composite start date
        start = datetime.strptime(image_id, "%Y_%m_%d").date()
        for band in BANDS:
            v = r[idx[band]]
            records.append(
                {
                    "date_key": image_id,
                    "date": start,
                    "variable": band,
                    "unit": "1" if band in VI_BANDS else ("day of year" if band == "DayOfYear" else "bit field"),
                    "raw_value": None if v is None else float(v),
                }
            )
    first = rows[0]
    center = (float(first[idx["longitude"]]), float(first[idx["latitude"]])) if "longitude" in idx else None
    return ModisRaw(pd.DataFrame(records), center, payload.get("request", {}))


# --------------------------------------------------------------------------- QA


def decode_detailed_qa(value: int) -> dict[str, int]:
    """Split the MOD13 DetailedQA (VI Quality) bit field into named parts."""
    v = int(value)
    return {
        "vi_quality": v & 0b11,
        "usefulness": (v >> 2) & 0b1111,
        "aerosol": (v >> 6) & 0b11,
        "adjacent_cloud": (v >> 8) & 1,
        "brdf_corrected": (v >> 9) & 1,
        "mixed_clouds": (v >> 10) & 1,
        "land_water": (v >> 11) & 0b111,
        "possible_snow_ice": (v >> 14) & 1,
        "possible_shadow": (v >> 15) & 1,
    }


def process(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, ProcessingStep]:
    """Scale and QA-flag the VI values.

    Returns ``(observations, composites, step)``:
    - observations: long table for the DB (all bands; VI bands scaled, QA bands kept as raw integers).
    - composites: one row per composite with NDVI, EVI, acquisition date, SummaryQA label and ``qa_pass``,
      the shape season detection (M5) uses.
    """
    obs = raw.copy()
    obs["processed_value"] = obs["raw_value"]
    obs["quality_flag"] = QualityFlag.OK.value
    obs["value_kind"] = ValueKind.OBSERVED.value
    obs["imputation_method"] = None
    obs["flag_reason"] = None

    wide_qa = obs[obs.variable == "SummaryQA"].set_index("date")["raw_value"]
    is_vi = obs.variable.isin(VI_BANDS)
    raw_v = obs["raw_value"]
    missing = is_vi & (raw_v.isna() | (raw_v == FILL_VALUE))
    rejected = is_vi & ~missing & ((raw_v < VALID_RANGE[0]) | (raw_v > VALID_RANGE[1]))
    obs.loc[is_vi, "processed_value"] = raw_v[is_vi] * SCALE_FACTOR
    obs.loc[missing, ["processed_value", "quality_flag", "flag_reason"]] = [np.nan, QualityFlag.MISSING.value, "fill"]
    obs.loc[rejected, ["processed_value", "quality_flag", "flag_reason"]] = [
        np.nan,
        QualityFlag.REJECTED.value,
        f"outside valid range {VALID_RANGE}",
    ]
    sqa = obs["date"].map(wide_qa)
    contaminated = is_vi & ~missing & ~rejected & ~sqa.isin(QA_PASS)
    obs.loc[contaminated, "quality_flag"] = QualityFlag.FLAGGED.value
    obs.loc[contaminated, "flag_reason"] = "SummaryQA " + sqa[contaminated].map(
        lambda q: SUMMARY_QA.get(int(q), "unknown") if pd.notna(q) else "missing"
    )
    marginal = is_vi & ~missing & ~rejected & (sqa == 1)
    obs.loc[marginal, "flag_reason"] = "SummaryQA marginal (usable)"

    piv = obs.pivot(index="date", columns="variable", values="processed_value")
    flags = obs[obs.variable == "NDVI"].set_index("date")["quality_flag"]
    doy = piv.get("DayOfYear")
    composites = pd.DataFrame(
        {
            "composite_start": piv.index,
            "ndvi": piv["NDVI"].to_numpy(),
            "evi": piv["EVI"].to_numpy(),
            "summary_qa": [SUMMARY_QA.get(int(q), "unknown") if pd.notna(q) else "missing" for q in piv["SummaryQA"]],
            "qa_pass": [bool(pd.notna(q) and int(q) in QA_PASS) for q in piv["SummaryQA"]],
            "ndvi_flag": flags.reindex(piv.index).to_numpy(),
            "acquired": [
                _acquired(s, d) for s, d in zip(piv.index, doy if doy is not None else [None] * len(piv), strict=True)
            ],
        }
    ).reset_index(drop=True)
    composites.loc[composites["ndvi"].isna(), "qa_pass"] = False

    counts = composites["summary_qa"].value_counts().to_dict()
    step = ProcessingStep(
        name="modis_qa",
        params={
            "scale_factor": SCALE_FACTOR,
            "fill_value": FILL_VALUE,
            "valid_range": list(VALID_RANGE),
            "qa_pass_rule": "SummaryQA in {0 good, 1 marginal}",
            "summary_qa_counts": {str(k): int(v) for k, v in counts.items()},
            "composites": len(composites),
            "qa_pass": int(composites["qa_pass"].sum()),
            "missing": int(missing.sum()),
            "rejected": int(rejected.sum()),
        },
        affected_count=int(missing.sum() + rejected.sum() + contaminated.sum()),
        reason=(
            "Applied the 0.0001 scale factor to NDVI/EVI, decoded the -3000 fill as missing, rejected values "
            "outside the valid range, and flagged snow/ice and cloudy composites (kept, not deleted)."
        ),
    )
    return obs, composites, step


def _acquired(composite_start: date, doy: float | None) -> date | None:
    """Acquisition date from DayOfYear; a composite starting late December can hold January days."""
    if doy is None or pd.isna(doy) or doy < 1:
        return None
    d = date(composite_start.year, 1, 1) + timedelta(days=int(doy) - 1)
    if d < composite_start - timedelta(days=1):  # wrapped into the next year
        d = date(composite_start.year + 1, 1, 1) + timedelta(days=int(doy) - 1)
    return d


# --------------------------------------------------------------------------- source record


def build_source(snapshot: RawSnapshot, parsed: ModisRaw) -> Source:
    dates = parsed.observations["date"]
    center = parsed.pixel_center_lon_lat
    return Source(
        id=f"modis_{snapshot.sha256[:16]}",
        provider="NASA LP DAAC (MODIS Terra); accessed via Google Earth Engine",
        product="MOD13Q1 Vegetation Indices 16-Day L3 Global 250m",
        version="061",
        variables=list(BANDS),
        units={"NDVI": "1", "EVI": "1", "SummaryQA": "class", "DetailedQA": "bit field", "DayOfYear": "day"},
        kind=ValueKind.OBSERVED,
        spatial_resolution="250 m nominal (231.66 m sinusoidal pixel)",
        temporal_resolution="16-day composite",
        coverage_start=dates.min(),
        coverage_end=dates.max(),
        retrieved_at=snapshot.retrieved_at,
        url="https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1",
        doi=DOI,
        license="NASA data, no restrictions on reuse; cite the DOI",
        attribution=CITATION,
        qa_notes=(
            f"Pixel containing the site point; pixel centre lon/lat {center}. SummaryQA and DetailedQA kept as "
            "raw integer variables; scale factor 0.0001 applied to NDVI/EVI."
        ),
        limitations=(
            "One 250 m pixel (~5.4 ha) is about the size of a small field, so mixed pixels are likely. "
            "Low vegetation index is not proof of bare soil (harvest, irrigation, cloud or crop type can explain it). "
            "Composites pick one observation per 16 days."
        ),
        raw_path=snapshot.relative_path,
        raw_sha256=snapshot.sha256,
    )

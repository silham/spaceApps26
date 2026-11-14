"""Explain the NASA POWER weather record for the candidate sites (team explainer, not a result).

Usage:  uv run python scripts/explore_power_candidates.py
Output: results/explorer/power_candidates.json  (gitignored; consumed by the team explainer page)

Candidate points are illustrative locations in the two candidate regions named in the guide (D3 is
still open). ET0 here uses pyfao56's ASCE standardized short-reference equation as an explainer;
the engine's ET0 is owned by M4. Nothing here evaluates the held-out test years (validation plan §1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pyfao56.refet import ascedaily
from scipy.stats import linregress

from ftm.config import get_settings
from ftm.contracts.models import ValueKind
from ftm.data.adapters import nasa_power
from ftm.data.pipeline.run import run_daily_pipeline
from ftm.data.raw_cache import RawSnapshot, find_latest_raw
from ftm.provenance import sha256_file

START, END = date(1981, 1, 1), date(2025, 12, 31)
PARAMETERS = (*nasa_power.DEFAULT_PARAMETERS, "T2MDEW")
TEST_YEARS = (2020, 2025)  # held out for validation; shown descriptively, never evaluated here


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    region: str
    latitude: float
    longitude: float


CANDIDATES = (
    Candidate("kansas", "Western Kansas (near Garden City)", "Western Kansas, USA", 37.97, -100.87),
    Candidate("sri_lanka", "Sri Lanka dry zone (near Anuradhapura)", "North Central Province, Sri Lanka", 8.31, 80.40),
)


def load_raw(c: Candidate) -> RawSnapshot:
    name = nasa_power.raw_filename(c.latitude, c.longitude, START, END)
    existing = find_latest_raw(nasa_power.SOURCE_KEY, name)
    if existing is not None:
        root = get_settings().raw_dir
        retrieved = datetime.strptime(existing.parent.name, "%Y-%m-%d").replace(tzinfo=UTC)
        return RawSnapshot(existing, existing.relative_to(root.parent).as_posix(), sha256_file(existing), retrieved)
    return nasa_power.fetch_daily(c.latitude, c.longitude, START, END, PARAMETERS, timeout_s=300)


def daily_et0(wide: pd.DataFrame, lat: float, elevation_m: float) -> pd.Series:
    def one(r: pd.Series) -> float:
        cols = ["ALLSKY_SFC_SW_DWN", "T2M_MAX", "T2M_MIN", "T2MDEW", "WS2M"]
        if r[cols].isna().any():
            return np.nan  # never compute ET0 from a missing input
        return ascedaily("S", elevation_m, lat, r.name.timetuple().tm_yday, r.ALLSKY_SFC_SW_DWN,
                         r.T2M_MAX, r.T2M_MIN, tdew=r.T2MDEW, wndsp=r.WS2M, wndht=2.0)  # fmt: skip

    return wide.apply(one, axis=1)


def summarise(c: Candidate) -> dict[str, object]:
    snap = load_raw(c)
    parsed = nasa_power.parse_daily(snap.path.read_bytes())
    source = nasa_power.build_source(f"src_power_{c.key}", snap, parsed)
    res = run_daily_pipeline(parsed.observations, site_id=f"candidate_{c.key}", source_id=source.id,
                             fill_value=parsed.fill_value, start=START, end=END,
                             value_kind=ValueKind.REANALYSIS)  # fmt: skip
    obs = res.observations[res.observations.quality_flag != "duplicate"]
    wide = obs.pivot(index="date", columns="variable", values="processed_value")
    wide.index = pd.to_datetime(wide.index)
    wide["ET0"] = daily_et0(wide, c.latitude, parsed.elevation_m or 0.0)
    wide["year"], wide["month"] = wide.index.year, wide.index.month

    # Monthly totals per year, then climatology across years (mean and spread).
    monthly = wide.groupby(["year", "month"]).agg(
        rain=("PRECTOTCORR", lambda s: s.sum(min_count=len(s))),  # NaN if any day missing: no silent zeros
        et0=("ET0", lambda s: s.sum(min_count=len(s))),
        tmax=("T2M_MAX", "mean"),
        tmin=("T2M_MIN", "mean"),
        srad=("ALLSKY_SFC_SW_DWN", "mean"),
    )
    clim = monthly.groupby("month").agg(
        rain_mean=("rain", "mean"),
        rain_p10=("rain", lambda s: s.quantile(0.1)),
        rain_p90=("rain", lambda s: s.quantile(0.9)),
        et0_mean=("et0", "mean"),
        tmax_mean=("tmax", "mean"),
        tmin_mean=("tmin", "mean"),
        srad_mean=("srad", "mean"),
    )
    annual = wide.groupby("year").agg(
        rain=("PRECTOTCORR", lambda s: s.sum(min_count=len(s))),
        et0=("ET0", lambda s: s.sum(min_count=len(s))),
        tmean=("T2M_MAX", "mean"),
        max_daily_rain=("PRECTOTCORR", "max"),
        rain_days_ge_1mm=("PRECTOTCORR", lambda s: int((s >= 1).sum())),
    )
    annual["tmean"] = (wide.groupby("year")["T2M_MAX"].mean() + wide.groupby("year")["T2M_MIN"].mean()) / 2
    annual["balance"] = annual.rain - annual.et0

    def trend(col: str) -> dict[str, float]:
        s = annual[col].dropna()
        fit = linregress(s.index.to_numpy(dtype=float), s.to_numpy())
        return {"per_decade": round(float(fit.slope) * 10, 3), "p_value": round(float(fit.pvalue), 4)}

    driest = annual.balance.nsmallest(5)
    rain = wide["PRECTOTCORR"]
    return {
        "key": c.key,
        "label": c.label,
        "region": c.region,
        "request_point": {"lat": c.latitude, "lon": c.longitude},
        "grid_point": parsed.grid_point,
        "elevation_m": parsed.elevation_m,
        "source": json.loads(source.model_dump_json()),
        "processing_run": {"id": res.run.id, "version": res.run.version, "summary": res.run.summary},
        "journey": [json.loads(j.model_dump_json(exclude={"chart"})) for j in res.journey],
        "qa": res.run.steps[0].params["per_variable"],
        "gaps": res.gaps,
        "climatology": _records(clim.reset_index()),
        "annual": _records(annual.reset_index()),
        "trends": {"tmean_C": trend("tmean"), "et0_mm": trend("et0"), "rain_mm": trend("rain")},
        "driest_years": [{"year": int(y), "balance_mm": round(float(v), 1)} for y, v in driest.items()],
        "rain_days": {
            "share_of_days_with_rain_ge_1mm": round(float((rain >= 1).mean()), 3),
            "p95_daily_rain_mm": round(float(rain.quantile(0.95)), 1),
            "max_daily_rain_mm": round(float(rain.max()), 1),
        },
        "annual_cv": {
            "rain": round(float(annual.rain.std() / annual.rain.mean()), 3),
            "et0": round(float(annual.et0.std() / annual.et0.mean()), 3),
        },
    }


def _records(df: pd.DataFrame) -> list[dict[str, object]]:
    return [{k: (None if pd.isna(v) else round(float(v), 2)) for k, v in row.items()} for row in df.to_dict("records")]


def main() -> None:
    out_dir = get_settings().results_dir / "explorer"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "period": [START.isoformat(), END.isoformat()],
        "test_years_held_out": list(TEST_YEARS),
        "et0_method": "ASCE standardized short reference (pyfao56.refet.ascedaily), dew point for vapour pressure",
        "candidates": [summarise(c) for c in CANDIDATES],
    }
    path: Path = out_dir / "power_candidates.json"
    path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"wrote {path}")
    write_explainer_tables(payload, out_dir)


# --------------------------------------------------------------------------- team explainer tables

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# Declared screening rule for "review" years (a prompt to check, NOT a finding that the data is wrong).
SUSPECT_RAIN_FRACTION_OF_MEDIAN = 0.5
SUSPECT_MAX_DAY_QUANTILE = 0.1


def write_explainer_tables(payload: dict[str, object], out_dir: Path) -> None:
    """Flat tables ({rows, meta}) for the team explainer page; meta carries this script's code."""
    code = Path(__file__).read_text(encoding="utf-8")
    meta = [
        {"label": "explore_power_candidates.py", "value": code, "type": "code", "lang": "python"},
        {"label": "Input", "value": "NASA POWER daily point API (raw snapshots under data/raw/power/)"},
        {"label": "Generated", "value": str(payload["generated_at"])},
    ]
    summary, monthly, annual, quality = [], [], [], []
    for c in payload["candidates"]:  # type: ignore[attr-defined]
        site = c["key"]
        ann = pd.DataFrame(c["annual"])
        median_rain = ann.rain.median()
        maxday_floor = ann.max_daily_rain.quantile(SUSPECT_MAX_DAY_QUANTILE)
        for r in c["annual"]:
            year = int(r["year"])
            suspect = r["rain"] < SUSPECT_RAIN_FRACTION_OF_MEDIAN * median_rain and r["max_daily_rain"] <= maxday_floor
            annual.append({
                "site": site, "year": year, "rain_mm": r["rain"], "et0_mm": r["et0"],
                "balance_mm": r["balance"], "tmean_c": r["tmean"], "max_daily_rain_mm": r["max_daily_rain"],
                "rain_days": r["rain_days_ge_1mm"],
                "held_out": "yes" if TEST_YEARS[0] <= year <= TEST_YEARS[1] else "no",
                "review_flag": "suspect" if suspect else "",
            })  # fmt: skip
        for m in c["climatology"]:
            i = int(m["month"])
            monthly.append(
                {"site": site, "month": i, "month_name": MONTHS[i - 1], **{k: m[k] for k in m if k != "month"}}
            )
        steps = {s: c["journey"][n]["details"] for n, s in enumerate(("check", "clean", "handle_gaps"))}
        for var, q in c["qa"].items():
            gap = next((g for g in c["gaps"] if g["variable"] == var and not g["resolved"]), None)
            quality.append({
                "site": site, "variable": var, "unit": c["source"]["units"].get(var, ""),
                "expected": q["expected"], "received": q["received"], "missing": q["missing"],
                "rejected": steps["clean"]["rejected_per_variable"].get(var, 0), "duplicate": q["duplicate"],
                "unresolved_gap": f"{gap['start']} to {gap['end']}" if gap else "",
            })  # fmt: skip
        with_et0 = ann.dropna(subset=["et0"])
        summary.append({
            "site": site, "label": c["label"], "region": c["region"],
            "request_lat": c["request_point"]["lat"], "request_lon": c["request_point"]["lon"],
            "elevation_m": c["elevation_m"], "first_year": int(ann.year.min()), "last_year": int(ann.year.max()),
            "first_et0_year": int(with_et0.year.min()),
            "mean_rain_mm": round(float(ann.rain.mean()), 0), "mean_et0_mm": round(float(with_et0.et0.mean()), 0),
            "mean_balance_mm": round(float(with_et0.balance.mean()), 0),
            "rain_cv": c["annual_cv"]["rain"],
            "tmean_trend_c_decade": c["trends"]["tmean_C"]["per_decade"],
            "tmean_trend_p": c["trends"]["tmean_C"]["p_value"],
            "rain_trend_mm_decade": c["trends"]["rain_mm"]["per_decade"],
            "rain_trend_p": c["trends"]["rain_mm"]["p_value"],
            "share_rain_days": c["rain_days"]["share_of_days_with_rain_ge_1mm"],
            "values_missing": int(sum(q["missing"] for q in c["qa"].values())),
            "suspect_years": sum(1 for a in annual if a["site"] == site and a["review_flag"]),
            "api_version": c["source"]["version"], "retrieved_at": c["source"]["retrieved_at"],
            "raw_sha256": c["source"]["raw_sha256"], "processing_run_id": c["processing_run"]["id"],
        })  # fmt: skip
    for name, rows in (("summary", summary), ("monthly", monthly), ("annual", annual), ("quality", quality)):
        p = out_dir / f"explainer_{name}.json"
        p.write_text(json.dumps({"rows": rows, "meta": meta}, default=str, allow_nan=False), encoding="utf-8")
        print(f"wrote {p}")


if __name__ == "__main__":
    main()

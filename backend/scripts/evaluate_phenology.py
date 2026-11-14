"""Tune and evaluate season detection for a site against NASS Crop Progress (validation plan v1.2, section 2).

Usage (from backend/; Earth Engine signed in for the CDL crop labels; NASS_API_KEY in .env):
  uv run python scripts/evaluate_phenology.py --site-id ks-field-2

- Crop per year: USDA CDL at the site point (cached in results/validation/).
- Reference: NASS Kansas 50 % planted date for that year's crop; summer crops only (corn, sorghum, soybeans).
- Tuning: 2006-2014 (CDL coverage within the 2001-2014 tuning period). Development check: 2015-2019, no
  retuning. Held-out 2020-2025: not touched (phenology.tune / evaluate_starts refuse them).
Writes results/validation/phenology_<site>.json (Validation contract) and phenology_<site>.png.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from ftm.config import get_settings
from ftm.contracts.models import Validation
from ftm.data.adapters import nass_quickstats as nass
from ftm.data.vegetation import get_vi_composites
from ftm.db.models import SiteRow, ValidationRow
from ftm.db.session import get_engine
from ftm.validation.phenology import detect_seasons, evaluate_starts, tune

TUNING_YEARS = range(2006, 2015)
DEV_YEARS = range(2015, 2020)
SUMMER_CROPS = {"Corn": "CORN", "Sorghum": "SORGHUM", "Soybeans": "SOYBEANS"}
PEAK_MONTHS = (6, 7, 8, 9)
CDL_NAMES = {
    1: "Corn",
    4: "Sorghum",
    5: "Soybeans",
    24: "Winter wheat",
    236: "Dbl crop WinWht/Sorghum",
    26: "Dbl crop WinWht/Soybeans",
    225: "Dbl crop WinWht/Corn",
    61: "Fallow/idle",
    36: "Alfalfa",
}


def cdl_history(site_id: str, lat: float, lon: float) -> dict[int, str]:
    cache = get_settings().results_dir / "validation" / f"cdl_{site_id}.json"
    if cache.exists():
        return {int(k): v for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
    import ee

    ee.Initialize(project=get_settings().ee_project)
    p = ee.Geometry.Point([lon, lat])
    out: dict[int, str] = {}
    for y in range(2006, 2025):
        try:
            v = ee.Image(f"USDA/NASS/CDL/{y}").select("cropland").sample(p, 30).first().get("cropland").getInfo()
            out[y] = CDL_NAMES.get(v, f"CDL class {v}")
        except Exception:
            out[y] = "not available"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def references(history: dict[int, str], years: range) -> tuple[list[date], list[dict[str, object]]]:
    refs, rows = [], []
    progress: dict[str, pd.DataFrame] = {}
    for y in years:
        crop = history.get(y, "not available")
        commodity = SUMMER_CROPS.get(crop)
        if commodity is None:
            rows.append({"year": y, "cdl_crop": crop, "reference": None, "why_not_scored": _why(crop)})
            continue
        if commodity not in progress:
            snap = nass.fetch_progress_cached(commodity, "PCT PLANTED", state="KS", years=range(2006, 2020))
            progress[commodity] = nass.parse(snap.path.read_bytes())
        d = nass.date_at_pct(progress[commodity], y, 50)
        rows.append(
            {"year": y, "cdl_crop": crop, "reference": d, "why_not_scored": None if d else "50 % not bracketed"}
        )
        if d:
            refs.append(d)
    return refs, rows


def _why(crop: str) -> str:
    if crop == "Winter wheat":
        return "winter wheat: NASS planting is autumn, detected start is spring green-up"
    if crop.startswith("Dbl crop"):
        return "double crop after wheat: no matching state reference"
    return f"no reference for '{crop}'"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-id", required=True)
    args = ap.parse_args()
    with Session(get_engine()) as s:
        site = s.get(SiteRow, args.site_id)
        if site is None:
            raise SystemExit(f"unknown site {args.site_id!r}")
        lat, lon = site.latitude, site.longitude
        comps = get_vi_composites(args.site_id, session=s)

    history = cdl_history(args.site_id, lat, lon)
    tune_refs, tune_rows = references(history, TUNING_YEARS)
    dev_refs, dev_rows = references(history, DEV_YEARS)

    best, table = tune(comps, tune_refs, years=TUNING_YEARS, peak_months=PEAK_MONTHS)
    pre = comps[[d.year < 2020 for d in comps["composite_start"]]]  # held-out years never enter evaluation
    pre.attrs.update(comps.attrs)
    result = detect_seasons(pre, best)
    ev_tune = evaluate_starts(result.seasons, tune_refs, peak_months=PEAK_MONTHS)
    ev_dev = evaluate_starts(result.seasons, dev_refs, peak_months=PEAK_MONTHS)

    per_year = []
    for row in tune_rows + dev_rows:
        det = next(
            (x for x in result.seasons if x.peak.year == row["year"] and x.peak.month in PEAK_MONTHS and x.start), None
        )
        err = (det.start - row["reference"]).days if det and row["reference"] else None
        per_year.append(
            {
                **row,
                "detected_start": det.start if det else None,
                "detected_peak": det.peak if det else None,
                "error_days": err,
                "split": "tuning" if row["year"] in TUNING_YEARS else "development",
            }
        )
    py = pd.DataFrame(per_year)
    print("Tuning grid (best first):")
    print(table.head(6).to_string(index=False))
    print(f"\nChosen params: {best}")
    print("\nPer year:")
    print(
        py[["year", "split", "cdl_crop", "reference", "detected_start", "error_days", "why_not_scored"]].to_string(
            index=False
        )
    )
    for label, ev in (("Tuning", ev_tune), ("Dev", ev_dev)):
        print(
            f"{label:<7} (n={ev['n_reference']}): bias {ev['bias_days']} d, "
            f"median |err| {ev['median_abs_error_days']} d, detection {ev['detection_rate']}"
        )

    out = get_settings().results_dir / "validation"
    out.mkdir(parents=True, exist_ok=True)
    failures = [
        f"{r['year']}: {r['why_not_scored']}" for r in per_year if r["why_not_scored"] and r["cdl_crop"] in SUMMER_CROPS
    ]
    if ev_dev["n_reference"] < 3:
        failures.append(f"development check has only n={ev_dev['n_reference']} scored season(s): too few to judge")
    metrics = {
        "tuning_n": ev_tune["n_reference"],
        "tuning_detection_rate": ev_tune["detection_rate"],
        "tuning_bias_days": ev_tune["bias_days"],
        "tuning_median_abs_error_days": ev_tune["median_abs_error_days"],
        "dev_n": ev_dev["n_reference"],
        "dev_detection_rate": ev_dev["detection_rate"],
        "dev_bias_days": ev_dev["bias_days"],
        "dev_median_abs_error_days": ev_dev["median_abs_error_days"],
        "param_window": best.window,
        "param_polyorder": best.polyorder,
        "param_fraction": best.fraction,
    }
    # per-year points for the Validate card (metrics must be numbers, so encoded as day-of-year keys)
    for r in per_year:
        if r["reference"] is not None and r["detected_start"] is not None:
            metrics[f"ref_doy_{r['year']}"] = pd.Timestamp(r["reference"]).day_of_year
            metrics[f"det_doy_{r['year']}"] = pd.Timestamp(r["detected_start"]).day_of_year
    record = Validation(
        id=f"val_phenology_{args.site_id}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
        target="Season start (amplitude-threshold green-up) of spring-planted summer crops at the field",
        reference="USDA NASS Crop Progress, Kansas state level, date of 50 % planted for the CDL crop of that year",
        calibration_period=(date(2006, 1, 1), date(2014, 12, 31)),
        test_period=None,  # held-out 2020-2025 not evaluated yet (validation plan section 1)
        sample_count=int(ev_tune["n_reference"] + ev_dev["n_reference"]),
        metrics={k: float(v) for k, v in metrics.items() if v is not None},
        failures=failures,
        independence_notes=(
            "Reference is independent of MODIS (survey data) but is statewide, not this field, and measures planting, "
            "while the detected start measures canopy green-up, so a positive bias is expected. Crop labels come from "
            "USDA CDL (a classified map). Winter wheat and double-crop seasons are not scored. Tuning n is small."
        ),
    )
    (out / f"phenology_{args.site_id}.json").write_text(
        json.dumps(
            {
                "validation": json.loads(record.model_dump_json()),
                "per_year": json.loads(py.to_json(orient="records", date_format="iso")),
                "tuning_table": json.loads(table.to_json(orient="records")),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    _chart(py, out / f"phenology_{args.site_id}.png")
    with Session(get_engine()) as s, s.begin():
        s.add(
            ValidationRow(
                id=record.id,
                target=record.target[:200],
                reference=record.reference,
                payload=json.loads(record.model_dump_json()),
            )
        )
    print(f"stored validation record {record.id}")
    print(f"\nwrote {out / f'phenology_{args.site_id}.json'}")


def _chart(py: pd.DataFrame, path) -> None:  # type: ignore[no-untyped-def]
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scored = py[py.reference.notna() & py.detected_start.notna()]
    fig, ax = plt.subplots(figsize=(8.5, 3.6), constrained_layout=True)
    doy = lambda d: pd.Timestamp(d).day_of_year  # noqa: E731
    for split, color in (("tuning", "#2a78d6"), ("development", "#eb6834")):
        g = scored[scored.split == split]
        ax.scatter(
            g.year,
            [doy(d) for d in g.reference],
            marker="s",
            s=40,
            facecolor="none",
            edgecolor=color,
            linewidth=1.8,
            label=f"NASS KS 50 % planted ({split})",
        )
        ax.scatter(
            g.year,
            [doy(d) for d in g.detected_start],
            marker="o",
            s=40,
            color=color,
            label=f"detected green-up start ({split})",
        )
        for r in g.itertuples():
            ax.plot([r.year, r.year], [doy(r.reference), doy(r.detected_start)], color=color, lw=1, alpha=0.6)
    ax.set_xlabel("year (corn years only)")
    ax.set_ylabel("day of year")
    ax.set_title("ks-field-2: detected season start vs statewide planting date", loc="left", fontsize=10)
    ax.legend(fontsize=7.5, loc="upper left", ncol=2, frameon=False)
    ax.grid(alpha=0.3)
    fig.text(
        0.01,
        -0.02,
        "Sources: MODIS MOD13Q1 v061 (season detection); USDA NASS Crop Progress (Kansas); USDA CDL (crop per year).",
        fontsize=7,
        color="#52514e",
    )
    fig.savefig(path, dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    main()

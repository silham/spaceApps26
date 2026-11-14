"""Required validation tests. Owner: M5. Remove the skip as each one is implemented."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from ftm.validation.phenology import (
    PhenologyParams,
    TestPeriodLockedError,
    detect_seasons,
    evaluate_starts,
    extract_stage,
    tune,
)


def _series(years: range, *, cloud_every: int = 0, rng_seed: int = 0) -> tuple[pd.DataFrame, list[date]]:
    """Synthetic two-season NDVI: a spring peak (~day 140) and a summer peak (~day 240) each year."""
    rng = np.random.default_rng(rng_seed)
    rows, true_starts = [], []
    for y in years:
        for k in range(23):
            start = date(y, 1, 1) + timedelta(days=16 * k)
            doy = (start + timedelta(days=8)).timetuple().tm_yday
            v = 0.2 + 0.6 * np.exp(-(((doy - 140) / 25) ** 2)) + 0.55 * np.exp(-(((doy - 240) / 22) ** 2))
            rows.append({"composite_start": start, "ndvi": v + rng.normal(0, 0.01), "qa_pass": True})
        true_starts += [date(y, 1, 1) + timedelta(days=140 - 30), date(y, 1, 1) + timedelta(days=240 - 27)]
    df = pd.DataFrame(rows)
    if cloud_every:
        df.loc[df.index % cloud_every == 3, "qa_pass"] = False
    return df, true_starts


def test_detects_two_seasons_per_year_close_to_truth() -> None:
    comps, truth = _series(range(2005, 2010))
    res = detect_seasons(comps, PhenologyParams(5, 2, 0.3))
    ev = evaluate_starts(res.seasons, truth)
    assert ev["detection_rate"] >= 0.9
    assert ev["median_abs_error_days"] <= 16  # within one composite
    assert len(res.low_cover_windows) >= 5  # gaps between the two seasons / years


def test_phenology_uses_only_qa_passed_points() -> None:
    comps, _ = _series(range(2005, 2008))
    baseline = detect_seasons(comps).series["ndvi_qa"]
    poisoned = comps.copy()
    bad = poisoned.index % 7 == 3
    poisoned.loc[bad, "qa_pass"] = False
    poisoned.loc[bad, "ndvi"] = -1.0  # a cloudy value must never enter the curve
    res = detect_seasons(poisoned)
    assert res.series.loc[bad, "ndvi_qa"].isna().all()
    assert (res.series["ndvi_filled"].dropna() > -0.5).all()
    assert len(baseline) == len(res.series)


def test_long_gap_splits_series_and_is_not_bridged() -> None:
    comps, _ = _series(range(2005, 2008))
    comps.loc[30:34, "qa_pass"] = False  # 5 composites (80 days) missing
    res = detect_seasons(comps)
    assert res.series.loc[30:34, "ndvi_filled"].isna().all()
    assert res.series["segment"].max() >= 2


def test_short_gap_is_bridged_and_reported() -> None:
    comps, _ = _series(range(2005, 2007))
    comps.loc[8, "qa_pass"] = False  # one composite near the spring peak
    res = detect_seasons(comps)
    assert bool(res.series.loc[8, "bridged"])
    assert any("bridged" in n for s in res.seasons for n in s.notes)


def test_flat_signal_claims_no_season() -> None:
    flat = pd.DataFrame(
        {
            "composite_start": [date(2005, 1, 1) + timedelta(days=16 * k) for k in range(46)],
            "ndvi": 0.3,
            "qa_pass": True,
        }
    )
    res = detect_seasons(flat)
    assert res.seasons == []
    assert extract_stage(res).status.value == "unavailable"


def test_test_period_untouched_by_calibration() -> None:
    comps, truth = _series(range(2018, 2023))
    with pytest.raises(TestPeriodLockedError):
        tune(comps, truth, years=range(2018, 2023))
    with pytest.raises(TestPeriodLockedError):
        evaluate_starts([], [date(2021, 5, 1)])
    # default tuning years exclude the test period, and unlock is explicit
    evaluate_starts([], [date(2021, 5, 1)], unlock_test=True)


def test_tune_picks_from_declared_grid_only() -> None:
    comps, truth = _series(range(2005, 2012))
    params, table = tune(comps, truth)
    assert params.window in (5, 7, 9) and params.polyorder in (2, 3) and params.fraction in (0.2, 0.3, 0.5)
    assert len(table) == 18
    assert table.iloc[0]["median_abs_error_days"] == table["median_abs_error_days"].min()


def test_extract_stage_payload_has_caveats_and_markers() -> None:
    comps, _ = _series(range(2005, 2007))
    comps.attrs.update(source_ids=["modis_x"], processing_run_id="proc_x")
    stage = extract_stage(detect_seasons(comps))
    assert stage.stage.value == "extract" and stage.source_ids == ["modis_x"]
    assert stage.chart and stage.chart["seasons"] and "not proof of bare soil" in " ".join(stage.details["caveats"])


@pytest.mark.skip(reason="M5: coverage evaluation needs the M4 ensemble")
def test_coverage_reports_sample_count_and_width() -> None: ...


def test_peak_month_matching_ignores_seasons_peaking_elsewhere() -> None:
    comps, _ = _series(range(2005, 2008))
    res = detect_seasons(comps, PhenologyParams(5, 2, 0.3))
    # reference near the spring season's start; only summer-peaking (Jul-Sep) seasons may match it
    refs = [date(y, 4, 20) for y in range(2005, 2008)]
    spring = evaluate_starts(res.seasons, refs)
    summer_only = evaluate_starts(res.seasons, refs, peak_months=(7, 8, 9))
    assert abs(spring["median_abs_error_days"]) < 20
    assert summer_only["median_abs_error_days"] > 60  # matched to the later season, not the nearest one

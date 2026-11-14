"""Required pipeline tests (DEVELOPMENT_GUIDE.md section 6). Owner: M3."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from ftm.contracts.models import JourneyStageName, QualityFlag, ValueKind
from ftm.data.pipeline.clean import UnitMismatchError, clean
from ftm.data.pipeline.gaps import handle_gaps
from ftm.data.pipeline.qa import check
from ftm.data.pipeline.run import run_daily_pipeline

FILL = -999.0
START = date(2024, 1, 1)
UNITS = {"PRECTOTCORR": "mm/day", "T2M_MAX": "C", "T2M_MIN": "C"}


def _obs(series: dict[str, list[float | None]], start: date = START) -> pd.DataFrame:
    rows = [
        {
            "date_key": (start + timedelta(days=i)).strftime("%Y%m%d"),
            "date": start + timedelta(days=i),
            "variable": var,
            "unit": UNITS[var],
            "raw_value": v,
        }
        for var, values in series.items()
        for i, v in enumerate(values)
    ]
    return pd.DataFrame(rows)


def _end(n: int) -> date:
    return START + timedelta(days=n - 1)


def _run(obs: pd.DataFrame, n: int):  # type: ignore[no-untyped-def]
    return run_daily_pipeline(
        obs,
        site_id="site_test",
        source_id="src_test",
        fill_value=FILL,
        start=START,
        end=_end(n),
        value_kind=ValueKind.REANALYSIS,
    )


def _get(df: pd.DataFrame, var: str, day: int) -> pd.Series:
    return df[(df.variable == var) & (df.date == START + timedelta(days=day))].iloc[0]


def test_missing_rainfall_is_not_zero_filled() -> None:
    res = _run(_obs({"PRECTOTCORR": [0.0, 1.0, FILL, 3.0, 0.0]}), 5)
    row = _get(res.observations, "PRECTOTCORR", 2)
    assert np.isnan(row.processed_value)
    assert row.quality_flag == QualityFlag.MISSING.value
    assert _get(res.observations, "PRECTOTCORR", 0).processed_value == 0.0  # real zero stays zero
    gap = next(g for g in res.gaps if g["variable"] == "PRECTOTCORR")
    assert gap["resolved"] is False and "never interpolated" in str(gap["why_unresolved"])


def test_raw_values_unchanged_after_processing() -> None:
    obs = _obs({"T2M_MAX": [5.0, FILL, 7.0, 99.0, 6.0], "PRECTOTCORR": [0.0, -3.0, FILL, 1.0, 2.0]})
    before = obs.copy()
    res = _run(obs, 5)
    pd.testing.assert_frame_equal(obs, before)  # input not mutated
    merged = before.merge(res.observations, on=["variable", "date"], suffixes=("_in", "_out"))
    assert merged["raw_value_in"].equals(merged["raw_value_out"])


def test_fill_values_and_scale_factors_decoded() -> None:
    # POWER has no scale factor; fill values are decoded to missing. (MODIS scale factors: MOD13Q1 adapter.)
    df, step = check(_obs({"T2M_MAX": [FILL, 4.0]}), fill_value=FILL, start=START, end=_end(2),
                     value_kind=ValueKind.REANALYSIS)  # fmt: skip
    assert np.isnan(_get(df, "T2M_MAX", 0).processed_value)
    assert _get(df, "T2M_MAX", 0).raw_value == FILL
    assert step.params["per_variable"]["T2M_MAX"]["missing"] == 1


def test_duplicates_flagged_not_dropped_silently() -> None:
    obs = _obs({"T2M_MAX": [5.0, 6.0]})
    obs = pd.concat([obs, obs.iloc[[1]].assign(raw_value=6.5)], ignore_index=True)
    df, step = check(obs, fill_value=FILL, start=START, end=_end(2), value_kind=ValueKind.REANALYSIS)
    assert len(df) == 3  # nothing dropped
    assert (df.quality_flag == QualityFlag.DUPLICATE.value).sum() == 1
    assert step.params["conflicting_duplicates"] == 1


def test_estimated_values_are_flagged_with_method() -> None:
    res = _run(_obs({"T2M_MAX": [10.0, FILL, FILL, 16.0, 12.0]}), 5)
    row = _get(res.observations, "T2M_MAX", 1)
    assert row.quality_flag == QualityFlag.ESTIMATED.value
    assert row.value_kind == ValueKind.ESTIMATED.value
    assert row.imputation_method == "linear_interpolation_max_2d"
    assert row.processed_value == pytest.approx(12.0)
    assert _get(res.observations, "T2M_MAX", 2).processed_value == pytest.approx(14.0)


def test_long_and_edge_gaps_left_unresolved() -> None:
    res = _run(_obs({"T2M_MAX": [FILL, 5.0, FILL, FILL, FILL, 9.0]}), 6)
    reasons = {g["start"]: g for g in res.gaps}
    assert not reasons["2024-01-01"]["resolved"] and "start or end" in str(reasons["2024-01-01"]["why_unresolved"])
    assert not reasons["2024-01-03"]["resolved"] and reasons["2024-01-03"]["length_days"] == 3
    assert res.observations[res.observations.variable == "T2M_MAX"].processed_value.isna().sum() == 4


def test_absent_days_become_explicit_missing_rows() -> None:
    obs = _obs({"T2M_MAX": [5.0, 6.0]})  # 2 delivered, 4 expected
    df, _ = check(obs, fill_value=FILL, start=START, end=_end(4), value_kind=ValueKind.REANALYSIS)
    assert len(df) == 4
    assert (df.flag_reason == "not delivered by source").sum() == 2
    assert df[df.flag_reason == "not delivered by source"].raw_value.isna().all()


def test_impossible_values_rejected_not_clipped() -> None:
    res = _run(_obs({"PRECTOTCORR": [1.0, -3.0, 2.0], "T2M_MAX": [5.0, 99.0, 6.0]}), 3)
    rain = _get(res.observations, "PRECTOTCORR", 1)
    assert rain.quality_flag == QualityFlag.REJECTED.value and np.isnan(rain.processed_value)
    assert rain.raw_value == -3.0
    # Rejected temperature becomes a 1-day gap and is then estimated (flagged as such).
    assert _get(res.observations, "T2M_MAX", 1).quality_flag == QualityFlag.ESTIMATED.value


def test_tmin_above_tmax_flagged() -> None:
    df, _ = check(_obs({"T2M_MAX": [5.0, 6.0], "T2M_MIN": [1.0, 8.0]}), fill_value=FILL, start=START,
                  end=_end(2), value_kind=ValueKind.REANALYSIS)  # fmt: skip
    df, step = clean(df)
    assert step.params["tmin_above_tmax_days"] == 1
    assert _get(df, "T2M_MIN", 1).quality_flag == QualityFlag.FLAGGED.value


def test_unit_mismatch_stops_the_run() -> None:
    obs = _obs({"T2M_MAX": [5.0]}).assign(unit="K")
    df, _ = check(obs, fill_value=FILL, start=START, end=_end(1), value_kind=ValueKind.REANALYSIS)
    with pytest.raises(UnitMismatchError):
        clean(df)


def test_zero_max_gap_fills_nothing() -> None:
    df, _ = check(_obs({"T2M_MAX": [1.0, FILL, 3.0]}), fill_value=FILL, start=START, end=_end(3),
                  value_kind=ValueKind.REANALYSIS)  # fmt: skip
    df, step, _ = handle_gaps(clean(df)[0], max_gap_days=0)
    assert step.affected_count == 0


def test_journey_payloads_and_provenance() -> None:
    res = _run(_obs({"PRECTOTCORR": [0.0, FILL, 1.0], "T2M_MAX": [5.0, FILL, 7.0]}), 3)
    stages = {s.stage: s for s in res.journey}
    assert set(stages) == {JourneyStageName.CHECK, JourneyStageName.CLEAN, JourneyStageName.HANDLE_GAPS}
    assert all(s.processing_run_id == res.run.id and s.source_ids == ["src_test"] for s in res.journey)
    assert [s.name for s in res.run.steps] == ["qa", "clean", "handle_gaps"]
    assert (res.observations.processing_run_id == res.run.id).all()
    assert stages[JourneyStageName.HANDLE_GAPS].status.value == "warning"  # rain gap unresolved

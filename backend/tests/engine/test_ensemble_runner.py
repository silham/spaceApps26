"""Paired ensemble, determinism, schedules and the engine runner's contract output. Owner: M4."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ftm.contracts.models import RANGE_LABEL, SimulationMode, Site
from ftm.engine.demo import DEMO_FORCING_ID, DEMO_FORCING_SOURCE, synthetic_forcing
from ftm.engine.ensemble import (
    MIN_PATHS_FOR_RANGE,
    SoilRunConfig,
    build_path_forcing,
    daily_weather,
    path_metrics,
    run_ensemble,
    run_strategies_on_path,
)
from ftm.engine.et0 import compute_et0
from ftm.engine.forcing import assert_forcing_contract
from ftm.engine.rotation import FALLOW_COVER, PathWeather, daily_schedule
from ftm.engine.runner import EngineInputError, EngineRequest, run_engine

from ._synthetic import IRR, crop, make_forcing, soil, strategy

HORIZON = (date(2027, 1, 1), date(2028, 12, 31))
STRATS = [
    strategy(
        "base",
        [("crop-a", date(2027, 4, 1), date(2027, 8, 31), IRR), ("crop-a", date(2028, 4, 1), date(2028, 8, 31), IRR)],
    ),
    strategy(
        "alt",
        [("crop-b", date(2027, 5, 1), date(2027, 9, 30), None), ("crop-a", date(2028, 4, 1), date(2028, 8, 31), IRR)],
    ),
]
CROPS = {"crop-a": crop("crop-a"), "crop-b": crop("crop-b", p=0.6, root=1.4)}
CONFIG = SoilRunConfig(soil=soil(), initial_fraction=0.5)


def _forcing_et0() -> tuple[pd.DataFrame, pd.DataFrame]:
    f = make_forcing("1990-01-01", "2005-12-31", seed=3)
    assert_forcing_contract(f)
    return f, compute_et0(f, latitude_deg=38.0, elevation_m=800.0)


def _path(years: tuple[int, ...] = (1995, 2001)) -> pd.DataFrame:
    f, e = _forcing_et0()
    return build_path_forcing(daily_weather(f, e), years, anchor_md="01-01", base_year=2027)


def test_strategies_share_identical_forcing() -> None:
    pf = _path()
    traces, _ = run_strategies_on_path(
        pf, STRATS, CROPS, CONFIG, mode=SimulationMode.IRRIGATION_NEEDED, allocation_mm_per_season=None
    )
    a, b = traces["base"], traces["alt"]
    assert len(a) == len(b) == len(pf)
    for col in ("rain_mm", "et0_mm", "source_date", "strategy_date"):
        assert (a[col].to_numpy() == b[col].to_numpy()).all()
    # Real historical days only: block 0 is 1995, block 1 is 2001.
    assert pd.Timestamp(a["source_date"].iloc[0]).year == 1995
    assert pd.Timestamp(a["source_date"].iloc[-1]).year == 2001


def test_same_seed_same_result() -> None:
    f, e = _forcing_et0()
    kw = {"horizon": HORIZON, "mode": SimulationMode.FIXED_ALLOCATION, "allocation_mm_per_season": 120.0, "n_paths": 8}
    _, r1 = run_ensemble(f, e, STRATS, CROPS, CONFIG, seed=42, **kw)  # type: ignore[arg-type]
    _, r2 = run_ensemble(f, e, STRATS, CROPS, CONFIG, seed=42, **kw)  # type: ignore[arg-type]
    _, r3 = run_ensemble(f, e, STRATS, CROPS, CONFIG, seed=7, **kw)  # type: ignore[arg-type]
    assert [o.years for o in r1] == [o.years for o in r2]
    assert [o.metrics for o in r1] == [o.metrics for o in r2]
    assert [o.years for o in r1] != [o.years for o in r3]


def test_path_metrics_count_cover_and_shortfall_correctly() -> None:
    pf = _path()
    traces, notes = run_strategies_on_path(
        pf, STRATS, CROPS, CONFIG, mode=SimulationMode.FIXED_ALLOCATION, allocation_mm_per_season=30.0
    )
    m = path_metrics(traces["base"])
    # Two seasons of 1 Apr-31 Aug (153 days each); the 20-day FAO-56 initial stage is not cover.
    assert m["cover_days"] == 2 * (153 - 20)
    assert m["cover_days"] + m["possible_low_cover_days"] == len(pf)
    assert m["crop_diversity_count"] == 1
    assert path_metrics(traces["alt"])["crop_diversity_count"] == 2
    assert m["irrigation_mm"] <= 2 * 30.0 + 1e-9
    assert 0 <= m["allocation_shortfall_days"] <= 2 * 153
    # crop-b roots (1.4 m) exceed the 1.0 m soil data depth: capped and disclosed.
    assert any("capped at 1 m" in n for n in notes["alt"]) and not notes["base"]


def test_schedule_uses_fallow_bare_soil_and_crop_parameters() -> None:
    pf = _path()
    dates = pd.DatetimeIndex(pf["strategy_date"])
    weather = PathWeather(*(pf[c].to_numpy(dtype="float64") for c in ("rain_mm", "et0_mm", "u2_m_s", "rhmin_pct")))
    sch = daily_schedule(STRATS[0], CROPS, soil(), dates, weather)
    fallow = ~sch.crop_day
    assert np.allclose(sch.zr_m[fallow], 0.15) and np.allclose(sch.zr_m[sch.crop_day], 0.8)
    assert (sch.cn[fallow] == 86).all() and (sch.cn[sch.crop_day] == 78).all()  # TR-55 B: bare fallow, row crop
    assert FALLOW_COVER == "fallow_bare_soil"
    assert np.isfinite(sch.kc).all() and ((sch.kc[fallow] >= 0) & (sch.kc[fallow] <= 1.15)).all()
    assert np.isnan(sch.p_table[fallow]).all() and (sch.p_table[sch.crop_day] == 0.5).all()
    mid = sch.kc[sch.crop_day].max()
    assert mid != pytest.approx(1.1)  # Kc mid adjusted to the path's wind and RHmin (FAO-56 eq. 62)


def _site() -> Site:
    return Site(id="test-site", name="Test", latitude=38.0, longitude=-100.0, timezone="UTC")


def _request(**over: object) -> EngineRequest:
    f = make_forcing("1990-01-01", "2005-12-31", seed=3)
    src = DEMO_FORCING_SOURCE.model_copy(update={"id": "test-src"})
    base: dict[str, object] = {
        "site": _site(),
        "elevation_m": 800.0,
        "elevation_note": "test",
        "forcing": f,
        "weather_source": src,
        "soil": soil(),
        "crops": CROPS,
        "strategies": STRATS,
        "horizon": HORIZON,
        "mode": SimulationMode.FIXED_ALLOCATION,
        "allocation_mm_per_season": 100.0,
        "initial_fraction": 0.5,
        "n_paths": MIN_PATHS_FOR_RANGE,
        "seed": 1,
    }
    base.update(over)
    return EngineRequest(**base)  # type: ignore[arg-type]


def test_runner_returns_contracts_with_sources_and_range_label() -> None:
    out = run_engine(_request())
    assert out.run.n_paths == MIN_PATHS_FOR_RANGE and out.run.input_versions["weather_processing_run_id"] == "test-run"
    assert out.run.is_demo  # weather source is DEMO
    assert {r.strategy_id for r in out.results} == {"base", "alt"}
    for r in out.results:
        assert r.range_label == RANGE_LABEL and r.sample_count == MIN_PATHS_FOR_RANGE
        assert r.p10 is not None and r.p90 is not None and r.p10 <= r.p50 <= r.p90  # type: ignore[operator]
        assert r.source_ids[:2] == ["test-src", "test-soil-src"] and "lit-fao56-1998" in r.source_ids
    assert {r.metric for r in out.results} >= {"irrigation_mm", "allocation_shortfall_days", "cover_days"}
    assert out.journey.stage.value == "simulate" and out.journey.processing_run_id == "test-run"


def test_too_few_paths_reports_no_range() -> None:
    out = run_engine(_request(n_paths=MIN_PATHS_FOR_RANGE - 1))
    assert all(r.p10 is None and r.p90 is None and r.p50 is not None for r in out.results)
    assert any("not reported below" in lim for lim in out.results[0].limitations)


def test_infeasible_strategy_gets_null_results_with_reasons() -> None:
    bad = strategy("bad", [("crop-a", date(2027, 4, 1), date(2027, 5, 1), IRR)])  # 30 days < 110 needed
    out = run_engine(_request(strategies=[*STRATS, bad]))
    rows = [r for r in out.results if r.strategy_id == "bad"]
    assert rows and all(r.p50 is None and r.sample_count == 0 for r in rows)
    assert any("needs 110 days" in lim for lim in rows[0].limitations)
    assert out.journey.status.value == "warning"
    only_bad = run_engine(_request(strategies=[bad]))
    assert only_bad.journey.status.value == "failed" and only_bad.run.n_paths == 0


def test_irrigation_needed_mode_has_no_allocation_metric() -> None:
    out = run_engine(_request(mode=SimulationMode.IRRIGATION_NEEDED, allocation_mm_per_season=None, n_paths=3))
    assert "allocation_shortfall_days" not in {r.metric for r in out.results}


@pytest.mark.parametrize(
    ("over", "msg"),
    [
        ({"mode": SimulationMode.IRRIGATION_NEEDED}, "only used in fixed_allocation"),
        ({"allocation_mm_per_season": None}, "needs an allocation"),
        ({"elevation_m": float("nan")}, "elevation"),
        ({"n_paths": 0}, "n_paths"),
        ({"initial_fraction": 1.5}, "fraction"),
        ({"strategies": []}, "at least one strategy"),
        ({"horizon": (date(2028, 1, 1), date(2027, 1, 1))}, "horizon"),
    ],
)
def test_invalid_requests_are_rejected(over: dict[str, object], msg: str) -> None:
    with pytest.raises(EngineInputError, match=msg):
        run_engine(_request(**over))


def test_weather_must_match_its_declared_source() -> None:
    with pytest.raises(EngineInputError, match="does not match"):
        run_engine(_request(weather_source=DEMO_FORCING_SOURCE))
    with pytest.raises(EngineInputError, match="site"):
        run_engine(_request(site=_site().model_copy(update={"id": "other"})))


def test_replay_runs_one_window_and_refuses_a_disabled_one() -> None:
    f = make_forcing("1990-01-01", "2005-12-31", seed=3)
    f.loc[pd.Timestamp("1998-03-03"), "PRECTOTCORR"] = np.nan
    f.loc[pd.Timestamp("1998-03-03"), "PRECTOTCORR__flag"] = "missing"
    out = run_engine(_request(forcing=f, replay_years=(1995, 1996)))
    assert out.run.resampling_method == "consecutive_year_replay" and out.run.n_paths == 1
    assert all(r.p10 is None and r.p50 is not None for r in out.results)
    with pytest.raises(EngineInputError, match="Replay unavailable: 1998"):
        run_engine(_request(forcing=f, replay_years=(1997, 1998)))


def test_traces_are_written_as_parquet(tmp_path: Path) -> None:
    out = run_engine(_request(n_paths=2, trace_dir=tmp_path))
    paths = {r.trace_path for r in out.results}
    assert len(paths) == 2 and all(p and Path(p).exists() for p in paths)
    df = pd.read_parquet(next(p for p in paths if p))
    assert set(df["path"]) == {0, 1} and "storage_end_mm" in df.columns


def test_synthetic_demo_forcing_is_deterministic_and_separate_from_fixtures() -> None:
    a, b = synthetic_forcing("2000-01-01", "2001-12-31"), synthetic_forcing("2000-01-01", "2001-12-31")
    pd.testing.assert_frame_equal(a, b)
    assert assert_forcing_contract(a).source_id == DEMO_FORCING_ID != "demo-weather"
    assert DEMO_FORCING_SOURCE.is_demo and DEMO_FORCING_SOURCE.kind.value == "demo"

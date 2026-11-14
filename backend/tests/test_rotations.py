"""User-built rotations (D15): save, validation, replacement and a run with per-season yield. TEST ONLY data."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from ftm.api.services import prediction
from ftm.api.services import rotations as rot
from ftm.api.services import runs as svc
from ftm.contracts.models import (
    RotationInput,
    RotationSeasonInput,
    RotationsUpdate,
    RunRequest,
    Site,
    Source,
    ValueKind,
)
from ftm.data.engine_inputs import SiteEngineInputs
from ftm.data.store import upsert_site, upsert_source
from ftm.db.models import SiteRow, StrategyRow
from ftm.db.session import get_engine

from .engine._synthetic import make_forcing, soil

SITE = "test-site-rotations"


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        conn = get_engine().connect()
        conn.execute(text("select superseded from strategy limit 1"))
        conn.rollback()
    except Exception as exc:
        pytest.skip(f"no migrated Postgres available: {exc.__class__.__name__}")
    trans = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def farm(session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path) -> SiteRow:  # type: ignore[no-untyped-def]
    forcing = make_forcing("1981-01-01", "2025-12-31", seed=11)
    site = Site(id=SITE, name="TEST ONLY farm", latitude=-33.0, longitude=148.0, timezone="UTC")
    src = Source(
        id="test-src", provider="TEST", product="synthetic", variables=[], units={}, kind=ValueKind.DEMO, is_demo=True
    )
    upsert_site(session, site)
    upsert_source(session, src)
    session.flush()
    sp = soil(awc=150.0)
    inputs = SiteEngineInputs(site, src, sp.profile, sp, forcing, 300.0, "TEST ONLY elevation")
    monkeypatch.setattr(svc, "load_site_engine_inputs", lambda s, site_id: inputs)
    monkeypatch.setattr(prediction, "load_site_engine_inputs", lambda s, site_id: inputs)
    prediction._inputs_cache.clear()
    prediction._prediction_cache.clear()
    prediction._outlook_cache.clear()
    monkeypatch.setattr(svc, "_window_rain", lambda f, years, anchor="01-01": 400.0)
    svc._prepared_cache.clear()
    svc._et0_cache.clear()
    settings = svc.get_settings()
    monkeypatch.setattr(settings, "results_dir", tmp_path / "results")
    monkeypatch.setattr(settings, "exports_dir", tmp_path / "exports")
    row = session.get(SiteRow, SITE)
    assert row is not None
    return row


def _season(crop: str, plant: date, *, irrigated: bool = False, usual: float | None = None) -> RotationSeasonInput:
    return RotationSeasonInput(crop_id=crop, plant_date=plant, irrigated=irrigated, usual_yield_t_ha=usual)


def _three() -> RotationsUpdate:
    return RotationsUpdate(
        rotations=[
            RotationInput(
                name="Current: irrigated maize",
                seasons=[_season("maize-grain", date(2026, 10, 15), irrigated=True, usual=9.0)],
            ),
            RotationInput(name="Rainfed soybean", seasons=[_season("soybean", date(2026, 10, 20))]),
            RotationInput(
                name="Sorghum then wheat",
                seasons=[_season("sorghum-grain", date(2026, 10, 25)), _season("spring-wheat", date(2027, 7, 1))],
            ),
        ]
    )


def test_more_than_three_rotations_or_four_seasons_is_refused() -> None:
    one = RotationInput(name="A", seasons=[_season("maize-grain", date(2026, 5, 1))])
    with pytest.raises(ValidationError):
        RotationsUpdate(rotations=[one, one, one, one])
    with pytest.raises(ValidationError):
        RotationInput(name="A", seasons=[_season("maize-grain", date(2026, 5, 1))] * 5)


def test_unknown_crop_late_date_and_unavailable_crop_are_refused(session: Session, farm: SiteRow) -> None:
    def one(season: RotationSeasonInput) -> RotationsUpdate:
        return RotationsUpdate(rotations=[RotationInput(name="A", seasons=[season])])

    with pytest.raises(rot.RotationError, match="unknown crop"):
        rot.save_rotations(session, farm, one(_season("quinoa", date(2026, 5, 1))))
    with pytest.raises(rot.RotationError, match="outside the comparison period"):
        rot.save_rotations(session, farm, one(_season("maize-grain", date(2030, 5, 1))))
    farm.farmer_context = {"available_crop_ids": ["soybean"]}
    with pytest.raises(rot.RotationError, match="not among the crops you said you can grow"):
        rot.save_rotations(session, farm, one(_season("maize-grain", date(2026, 5, 1))))


def test_saving_replaces_the_active_set_but_keeps_old_rows(session: Session, farm: SiteRow) -> None:
    first = rot.save_rotations(session, farm, _three())
    assert [s.is_baseline for s in first] == [True, False, False]
    assert [s.id[:4] for s in first] == ["rot0", "rot1", "rot2"]
    replacement = RotationsUpdate(rotations=[_three().rotations[1]])
    second = rot.save_rotations(session, farm, replacement)
    active = rot.active_strategies(session, SITE)
    assert [s.id for s in active] == [s.id for s in second]
    assert session.get(StrategyRow, first[0].id) is not None  # old row stays: earlier results reference it
    assert session.get(StrategyRow, first[0].id).superseded  # type: ignore[union-attr]
    # Saving the identical set again is idempotent.
    assert [s.id for s in rot.save_rotations(session, farm, replacement)] == [s.id for s in second]


def test_run_on_user_rotations_reports_water_soil_and_yield(session: Session, farm: SiteRow) -> None:
    saved = rot.save_rotations(session, farm, _three())
    detail = svc.create_run(session, RunRequest(site_id=SITE, n_paths=20))
    assert [s.id for s in detail.strategies] == [s.id for s in saved]
    assert all(s.feasibility and s.feasibility.feasible for s in detail.strategies), [
        s.feasibility for s in detail.strategies
    ]
    results = svc.get_results(session, detail.run.id)
    by = {(r.strategy_id, r.metric, r.season_index): r for r in results}
    maize, soy, sorg = (s.id for s in saved)

    for sid in (maize, soy, sorg):  # water and soil metrics exist for every rotation
        for metric in ("irrigation_mm", "water_stress_days", "possible_low_cover_days"):
            assert (sid, metric, None) in by
    assert by[(soy, "irrigation_mm", None)].p50 == 0  # rainfed: no irrigation was ever added

    rel = by[(maize, "relative_yield_pct", 0)]
    assert rel.crop_id == "maize-grain" and rel.p50 is not None and 0 <= rel.p50 <= 100
    assert rel.p10 is not None and rel.p90 is not None and rel.p10 <= rel.p50 <= rel.p90
    assert (maize, "yield_t_ha", 0) in by and by[(maize, "yield_t_ha", 0)].unit == "t/ha"
    assert (soy, "yield_t_ha", 0) not in by  # no usual yield entered, so no t/ha
    assert {r.season_index for r in results if r.strategy_id == sorg and r.metric == "relative_yield_pct"} == {0, 1}
    assert by[(maize, "relative_yield_pct", 0)].p50 == pytest.approx(100.0)  # refilled to field capacity: no deficit
    assert by[(soy, "relative_yield_pct", 0)].p50 < 100.0  # rainfed on dry synthetic weather loses some yield
    assert any("Tonnes per hectare" in line for line in rel.limitations)
    assert svc.create_run(session, RunRequest(site_id=SITE, n_paths=20)).run.id == detail.run.id  # cached


def test_a_farm_with_no_saved_rotations_stays_observe_only(session: Session, farm: SiteRow) -> None:
    with pytest.raises(svc.SiteNotReadyError, match="observe-only"):
        svc.create_run(session, RunRequest(site_id=SITE, n_paths=20))


def test_outlook_and_run_use_the_real_calendar_without_a_forecast(session: Session, farm: SiteRow) -> None:
    out = prediction.outlook_for(session, SITE)
    assert out.horizon_start == date(2026, 1, 1) and out.observed_end == date(2025, 12, 31)
    assert out.forecast_source_id is None and out.odds == []  # no snapshot: past years equally likely, stated
    assert any("equally likely" in a for a in out.assumptions)
    assert "bare fallow" in out.initial_assumption
    assert 0 <= out.soil_water_now_mm <= out.soil_water_capacity_mm
    assert out.dates[0] == date(2026, 1, 1) and len(out.rain_mm.p50) == len(out.dates)
    rot.save_rotations(session, farm, _three())
    detail = svc.create_run(session, RunRequest(site_id=SITE, n_paths=20))
    iv = detail.run.input_versions
    assert iv["horizon"] == "2026-01-01 to 2027-12-31" and iv["initial_state"].startswith("observed")
    replay = svc.replay(session, detail.run.id, tuple(detail.replay_windows[0].years))
    assert replay.dates[0] == date(2026, 1, 1)


def test_field_now_crop_changes_soil_water_now(session: Session, farm: SiteRow) -> None:
    bare = prediction.outlook_for(session, SITE)
    farm.farmer_context = {"current_crop_id": "maize-grain", "current_plant_date": "2025-09-01"}
    session.flush()
    cropped = prediction.outlook_for(session, SITE)
    assert "farmer input" in cropped.initial_assumption
    assert cropped.soil_water_now_mm <= bare.soil_water_now_mm


def test_crop_on_the_field_now_runs_ahead_of_every_rotation(session: Session, farm: SiteRow) -> None:
    # maize planted 2025-11-01 is still growing when the horizon starts (2026-01-01): it runs ahead of every rotation
    farm.farmer_context = {"current_crop_id": "maize-grain", "current_plant_date": "2025-11-01"}
    session.flush()
    early = RotationsUpdate(rotations=[RotationInput(name="Too early", seasons=[_season("soybean", date(2026, 2, 1))])])
    (blocked,) = rot.save_rotations(session, farm, early)
    assert blocked.feasibility and not blocked.feasibility.feasible
    assert any("crop on the field now" in r for r in blocked.feasibility.reasons)
    rot.save_rotations(session, farm, _three())
    detail = svc.create_run(session, RunRequest(site_id=SITE, n_paths=20))
    assert "standing_season" in detail.run.input_versions
    results = svc.get_results(session, detail.run.id)
    seasons = {r.season_index for r in results if r.metric == "relative_yield_pct"}
    assert seasons == {0, 1}  # the standing maize adds no yield result; rotation seasons keep their numbers
    assert any("crop on the field now" in lim for lim in results[0].limitations)
    replay = svc.replay(session, detail.run.id, tuple(detail.replay_windows[0].years))
    assert any(c == "maize-grain" for c in replay.series[1].crop_id[:30])  # rotation 2 starts under the maize


def test_suggestions_job_on_a_southern_farm(session: Session, farm: SiteRow) -> None:
    from datetime import UTC, datetime

    from ftm.api.services import recommendations as rec
    from ftm.contracts.models import RecommendationJob, RecommendationRequest
    from ftm.engine.recommend import in_table11_months

    rot.save_rotations(session, farm, _three())
    req = RecommendationRequest(max_seasons=2, priorities=["soil_health", "cover", "irrigation"])
    job = RecommendationJob(
        id="rec_test", site_id=SITE, status="running", progress=0, request=req, created_at=datetime.now(UTC)
    )
    rec._jobs[job.id] = job
    rec._compute(session, job.id)  # the job thread opens its own session; call the work directly
    out = rec._jobs.pop(job.id)
    assert out.status == "done" and out.candidates, out.message
    crops = rot.selectable_crops()
    for c in out.candidates:
        assert all(in_table11_months(crops[s.crop_id], s.plant_date, True) for s in c.seasons if s.crop_id)
        assert c.soil_health and c.why
    assert any(a.startswith("Groundnut (peanut) is not suggested") for a in out.assumptions)
    ranks = [c.rank for c in out.candidates]
    assert ranks == sorted(ranks)
    if out.current_practice is not None:  # bullets use the same per-path difference as the metric line
        c = out.candidates[0]
        irr = next(m for m in c.metrics if m.metric == "irrigation_mm")
        if irr.delta_p50_vs_current and abs(irr.delta_p50_vs_current) >= 1:
            assert any(f"{abs(irr.delta_p50_vs_current):.0f} mm" in t for t in c.trade_offs)

"""Runs, paired comparison, replay and decision cards (M1). Synthetic TEST-ONLY inputs, never real data.

DB-backed tests run inside a rolled-back transaction and skip when no migrated Postgres is reachable.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from ftm.api.main import app
from ftm.api.services import decisions as card_svc
from ftm.api.services import runs as svc
from ftm.contracts.models import (
    DecisionCardRequest,
    ReplaySeries,
    RunRequest,
    Site,
    Source,
    ValueKind,
)
from ftm.data.engine_inputs import SiteEngineInputs
from ftm.data.store import upsert_site, upsert_source
from ftm.db.session import get_engine, get_session
from ftm.engine.ensemble import PathOutcome
from ftm.engine.scenarios import build_ks_field_2

from .engine._synthetic import make_forcing, soil

client = TestClient(app)
SITE = "test-site-runs"


# --------------------------------------------------------------------------- request validation (no DB)


def test_run_request_accepts_only_d6_edits() -> None:
    RunRequest(site_id="s", planting_shift_days={"a": 14, "b": -14})
    with pytest.raises(ValidationError, match="±14"):
        RunRequest(site_id="s", planting_shift_days={"a": 15})
    with pytest.raises(ValidationError, match="needs an irrigation allocation"):
        RunRequest(site_id="s", mode="fixed_allocation")
    with pytest.raises(ValidationError, match="only in fixed_allocation"):
        RunRequest(site_id="s", allocation_mm=200)
    with pytest.raises(ValidationError):
        RunRequest(site_id="s", n_paths=10)  # below the path count that supports a range
    with pytest.raises(ValidationError):
        RunRequest(site_id="s", seed=1, crop="maize")  # type: ignore[call-arg]  # unsupported edit field


def test_unsupported_edit_is_422_before_any_engine_call() -> None:
    from ftm.api.auth import require_user
    from ftm.db.models import UserRow

    app.dependency_overrides[require_user] = lambda: UserRow(id="test")
    app.dependency_overrides[get_session] = lambda: None
    try:
        r = client.post(
            "/runs", json={"site_id": "s", "planting_shift_days": {"x": 20}}, headers={"X-FTM-Request": "1"}
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422
    assert "±14" in r.text


def test_replay_years_must_be_a_window() -> None:
    from ftm.api.auth import require_user
    from ftm.db.models import UserRow

    app.dependency_overrides[require_user] = lambda: UserRow(id="test")
    app.dependency_overrides[get_session] = lambda: None
    try:
        assert client.get("/runs/x/replay", params={"years": "dry"}).status_code == 422
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- paired comparison (no DB)


def _outcome(years: tuple[int, ...], base: float, alt: float) -> PathOutcome:
    return PathOutcome(
        years,
        {
            "base": {"irrigation_mm": base, "cover_days": 100.0, "aet_mm": 500.0},
            "alt": {"irrigation_mm": alt, "cover_days": 120.0, "aet_mm": 480.0},
        },
    )


def test_deltas_are_taken_per_path_not_from_medians() -> None:
    # Medians of each strategy are equal (both 100), but alt is 10 mm lower than base on every path.
    outcomes = [_outcome((y,), base=b, alt=b - 10) for y, b in zip(range(30), [90, 100, 110] * 10, strict=True)]
    units = {"irrigation_mm": "mm", "cover_days": "days", "aet_mm": "mm"}
    d = {x.metric: x for x in svc.deltas_from_outcomes("r", outcomes, "base", units, ["s"], is_demo=False)}
    assert d["irrigation_mm"].p10 == d["irrigation_mm"].p50 == d["irrigation_mm"].p90 == -10
    assert d["irrigation_mm"].share_better == 1.0 and d["irrigation_mm"].share_worse == 0.0
    assert d["cover_days"].better_direction == "higher" and d["cover_days"].share_better == 1.0
    assert d["aet_mm"].better_direction is None and d["aet_mm"].share_better is None  # no preferred direction
    assert all(x.strategy_id == "alt" and x.baseline_strategy_id == "base" for x in d.values())


def test_deltas_hide_range_below_min_paths() -> None:
    outcomes = [_outcome((y,), base=100, alt=90) for y in range(5)]
    (d,) = svc.deltas_from_outcomes("r", outcomes, "base", {"irrigation_mm": "mm"}, [], is_demo=False)
    assert d.p50 == -10 and d.p10 is None and d.p90 is None


def test_turning_point_is_the_day_of_largest_soil_water_difference() -> None:
    days = [date(2027, 1, d) for d in (1, 2, 3)]

    def s(sid: str, storage: list[float | None]) -> ReplaySeries:
        n = len(storage)
        return ReplaySeries(
            strategy_id=sid, crop_id=[None] * n, in_crop=[False] * n, storage_mm=storage, ks=[1.0] * n,
            irrigation_mm=[0.0] * n, aet_mm=[0.0] * n, metrics={},
        )  # fmt: skip

    tp, why = svc.turning_point([s("a", [100, 100, 90]), s("b", [100, 60, 80])], days)
    assert tp == date(2027, 1, 2) and why is not None and "40 mm" in why
    assert svc.turning_point([s("a", [1, 2, 3])], days) == (None, None)


# --------------------------------------------------------------------------- lifecycle on a real DB


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        conn = get_engine().connect()
        conn.execute(text("select detail from simulation_run limit 1"))
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
def synthetic_site(session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path) -> SiteEngineInputs:  # type: ignore[no-untyped-def]
    forcing = make_forcing("1981-01-01", "2025-12-31", seed=11)
    site = Site(id=SITE, name="TEST ONLY synthetic site", latitude=38.0, longitude=-100.9, timezone="UTC")
    src = Source(
        id="test-src", provider="TEST", product="synthetic weather", variables=[], units={},
        kind=ValueKind.DEMO, is_demo=True,
    )  # fmt: skip
    upsert_site(session, site)
    upsert_source(session, src)
    session.flush()
    sp = soil(awc=200.0)
    inputs = SiteEngineInputs(site, src, sp.profile, sp, forcing, 850.0, "TEST ONLY elevation")
    scen = build_ks_field_2(forcing, list(range(1984, 2020)), site_id=SITE)
    monkeypatch.setattr(svc, "load_site_engine_inputs", lambda s, site_id: inputs)
    monkeypatch.setattr(svc, "build_site_scenario", lambda i: scen)
    from ftm.data import engine_inputs

    monkeypatch.setitem(engine_inputs.SCENARIO_BUILDERS, SITE, build_ks_field_2)  # strategies "reviewed" for the test
    monkeypatch.setattr(svc, "_window_rain", lambda f, years, anchor="01-01": 400.0)
    svc._prepared_cache.clear()
    svc._et0_cache.clear()
    svc._replay_cache.clear()
    settings = svc.get_settings()
    monkeypatch.setattr(settings, "results_dir", tmp_path / "results")
    monkeypatch.setattr(settings, "exports_dir", tmp_path / "exports")
    return inputs


def test_run_lifecycle_cache_replay_and_decision_card(session: Session, synthetic_site: SiteEngineInputs) -> None:
    req = RunRequest(site_id=SITE, n_paths=20)
    detail = svc.create_run(session, req)
    assert not detail.cached and detail.run.n_paths == 20
    ids = [s.id for s in detail.strategies]
    assert ids == ["ks2-current-corn-wheat", "ks2-alt-a-double-crop", "ks2-alt-b-sorghum-wheat"]
    assert all(s.feasibility and s.feasibility.feasible for s in detail.strategies)

    # Identical request -> the stored run, not a new one.
    again = svc.create_run(session, req)
    assert again.cached and again.run.id == detail.run.id

    results = svc.get_results(session, detail.run.id)
    assert {r.strategy_id for r in results} == set(ids)
    assert all(r.source_ids and "test-src" in r.source_ids for r in results)
    deltas = svc.get_deltas(session, detail.run.id)
    assert deltas and {d.baseline_strategy_id for d in deltas} == {"ks2-current-corn-wheat"}

    # A planting shift is a different run with the shifted dates stored.
    shifted = svc.create_run(session, RunRequest(site_id=SITE, n_paths=20, planting_shift_days={ids[0]: 7}))
    assert shifted.run.id != detail.run.id
    base0, shift0 = detail.strategies[0].seasons[0], shifted.strategies[0].seasons[0]
    assert (shift0.plant_date - base0.plant_date).days == 7

    window = next(w for w in detail.replay_windows if w.enabled and w.in_sample_pool)
    trace = svc.replay(session, detail.run.id, tuple(window.years))
    assert len(trace.series) == 3 and len(trace.dates) == len(trace.rain_mm)
    assert all(len(s.storage_mm) == len(trace.dates) for s in trace.series)
    # Identical weather for every strategy: rain is one shared series.
    with pytest.raises(svc.RunBlockedError, match="not a replay window"):
        svc.replay(session, detail.run.id, (1900, 1901))

    card = card_svc.create_card(
        session,
        DecisionCardRequest(site_id=SITE, run_id=detail.run.id, chosen_strategy_id=ids[2], reason="TEST reason"),
    )
    assert card.chosen_strategy_id == ids[2] and card.run.id == detail.run.id
    assert "test-src" in {s.id for s in card.sources}
    assert card.local_review_questions and card.assumptions and card.limitations
    assert card.run.model_version and card.is_demo  # synthetic source is DEMO, so the card says so
    stored, row = card_svc.get_card(session, card.id)
    assert stored.reason == "TEST reason" and row.sha256
    assert (card_svc.exports_dir() / f"{card.id}.pdf").read_bytes().startswith(b"%PDF")

    with pytest.raises(card_svc.DecisionRefusedError, match="not part of run"):
        card_svc.create_card(
            session,
            DecisionCardRequest(site_id=SITE, run_id=detail.run.id, chosen_strategy_id="nope", reason="x"),
        )

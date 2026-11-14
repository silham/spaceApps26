"""Round-trip tests against a real Postgres (skipped when no migrated database is reachable).

Each test runs inside a transaction that is rolled back, so the database is left unchanged.
"""

from collections.abc import Iterator
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ftm.contracts.models import Site, Source, ValueKind
from ftm.data.forcing import FLAG_SUFFIX, ForcingNotAvailableError, get_daily_forcing
from ftm.data.pipeline.run import AlignContext, run_daily_pipeline
from ftm.data.store import save_pipeline_result, upsert_site, upsert_source
from ftm.db.models import ObservationRow
from ftm.db.session import get_engine

START = date(2024, 1, 1)


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        conn = get_engine().connect()
        conn.execute(text("select 1 from observation limit 1"))
    except Exception as exc:
        pytest.skip(f"no migrated Postgres available: {exc.__class__.__name__}")
    trans = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()


def _load(session: Session) -> str:
    upsert_site(session, Site(id="test-site", name="test", latitude=38.0, longitude=-100.0, timezone="America/Chicago"))
    upsert_source(
        session,
        Source(
            id="test-src",
            provider="test",
            product="test",
            variables=["PRECTOTCORR"],
            units={"PRECTOTCORR": "mm/day"},
            kind=ValueKind.REANALYSIS,
        ),
    )
    session.flush()
    obs = pd.DataFrame(
        {
            "date_key": [(START + timedelta(days=i)).strftime("%Y%m%d") for i in range(4)],
            "date": [START + timedelta(days=i) for i in range(4)],
            "variable": "PRECTOTCORR",
            "unit": "mm/day",
            "raw_value": [0.0, -999.0, 4.5, 1.0],
        }
    )
    res = run_daily_pipeline(
        obs,
        site_id="test-site",
        source_id="test-src",
        fill_value=-999.0,
        start=START,
        end=START + timedelta(days=3),
        value_kind=ValueKind.REANALYSIS,
        align=AlignContext("America/Chicago", "LST", None, None),
    )
    save_pipeline_result(session, res)
    session.flush()
    return res.run.id


def test_round_trip_keeps_raw_and_missing(session: Session) -> None:
    run_id = _load(session)
    rows = session.execute(
        select(ObservationRow.raw_value, ObservationRow.processed_value, ObservationRow.quality_flag)
        .where(ObservationRow.processing_run_id == run_id)
        .order_by(ObservationRow.observed_at)
    ).all()
    assert [r.raw_value for r in rows] == [0.0, -999.0, 4.5, 1.0]  # raw stored as delivered
    assert rows[1].processed_value is None and rows[1].quality_flag == "missing"  # NULL, never 0


def test_get_daily_forcing_returns_flags_and_provenance(session: Session) -> None:
    run_id = _load(session)
    wide = get_daily_forcing("test-site", START, START + timedelta(days=4), "test-src", session=session)
    assert wide.attrs["processing_run_id"] == run_id and wide.attrs["source_ids"] == ["test-src"]
    assert wide.loc[START, "PRECTOTCORR"] == 0.0
    assert np.isnan(wide.loc[START + timedelta(days=1), "PRECTOTCORR"])
    assert wide.loc[START + timedelta(days=4), "PRECTOTCORR" + FLAG_SUFFIX] == "missing"  # beyond stored data


def test_rerun_adds_a_new_run_and_keeps_the_old(session: Session) -> None:
    first = _load(session)
    second = _load(session)
    assert first != second
    counts = dict(
        session.execute(
            select(ObservationRow.processing_run_id, func.count())
            .where(ObservationRow.site_id == "test-site")
            .group_by(ObservationRow.processing_run_id)
        ).all()
    )
    assert counts == {first: 4, second: 4}


def test_unknown_source_raises(session: Session) -> None:
    _load(session)
    with pytest.raises(ForcingNotAvailableError):
        get_daily_forcing("test-site", START, START, "nope", session=session)

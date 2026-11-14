"""Data Journey assembly: Validate-stage logic (no DB) and the full assembler on Postgres (skips without DB)."""

from collections.abc import Iterator
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ftm.contracts.models import JourneyStageName, Site, Source, StageStatus, Validation, ValueKind
from ftm.data.journey import ORDER, SiteNotFoundError, build_journey
from ftm.data.pipeline.run import AlignContext, run_daily_pipeline
from ftm.data.store import save_pipeline_result, upsert_site, upsert_source
from ftm.db.session import get_engine
from ftm.validation.report import validate_stage


def _record(failures: list[str]) -> Validation:
    return Validation(
        id="val_phenology_x_1",
        target="t",
        reference="USDA NASS Crop Progress, Kansas",
        calibration_period=(date(2006, 1, 1), date(2014, 12, 31)),
        sample_count=7,
        metrics={
            "tuning_n": 5,
            "tuning_detection_rate": 1.0,
            "tuning_bias_days": 22.4,
            "dev_n": 2,
            "ref_doy_2006": 113,
            "det_doy_2006": 144,
            "ref_doy_2016": 122,
            "det_doy_2016": 136,
        },
        failures=failures,
        independence_notes="statewide reference",
    )


def test_validate_stage_reports_failures_and_what_is_not_evaluated() -> None:
    st = validate_stage([_record(["development check n=2"])])
    assert st.status == StageStatus.WARNING
    assert "5 of 5" in st.summary and "+22 days" in st.summary
    assert st.chart and [p["split"] for p in st.chart["points"]] == ["tuning", "development"]
    assert any("Held-out" in x for x in st.details["not_yet_evaluated"])
    assert "ref_doy_2006" not in st.details["metrics"]


def test_validate_stage_without_records_is_not_started() -> None:
    assert validate_stage([]).status == StageStatus.NOT_STARTED


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        conn = get_engine().connect()
        conn.execute(text("select 1 from observation limit 1"))
        conn.rollback()
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


def test_journey_with_weather_only(session: Session) -> None:
    upsert_site(session, Site(id="j-site", name="j", latitude=38.0, longitude=-100.0, timezone="America/Chicago"))
    upsert_source(
        session,
        Source(
            id="power_test",
            provider="p",
            product="p",
            variables=["PRECTOTCORR"],
            units={"PRECTOTCORR": "mm/day"},
            kind=ValueKind.REANALYSIS,
        ),
    )
    session.flush()
    start = date(2024, 1, 1)
    obs = pd.DataFrame(
        {
            "date_key": [(start + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)],
            "date": [start + timedelta(days=i) for i in range(3)],
            "variable": "PRECTOTCORR",
            "unit": "mm/day",
            "raw_value": [0.0, -999.0, 2.0],
        }
    )
    res = run_daily_pipeline(
        obs,
        site_id="j-site",
        source_id="power_test",
        fill_value=-999.0,
        start=start,
        end=start + timedelta(days=2),
        value_kind=ValueKind.REANALYSIS,
        align=AlignContext("America/Chicago", "LST", None, None),
    )
    save_pipeline_result(session, res)
    session.flush()

    stages = build_journey("j-site", session)
    assert [s.stage for s in stages] == ORDER and len(stages) == 9
    by = {s.stage: s for s in stages}
    assert by[JourneyStageName.COLLECT].status == StageStatus.WARNING  # soil + satellite missing
    assert "soil" in by[JourneyStageName.COLLECT].details["missing"]
    assert by[JourneyStageName.CHECK].processing_run_id == res.run.id
    assert by[JourneyStageName.EXTRACT].status == StageStatus.UNAVAILABLE
    assert by[JourneyStageName.VALIDATE].status == StageStatus.NOT_STARTED
    assert by[JourneyStageName.SIMULATE].status == StageStatus.NOT_STARTED


def test_unknown_site_raises(session: Session) -> None:
    with pytest.raises(SiteNotFoundError):
        build_journey("nope", session)

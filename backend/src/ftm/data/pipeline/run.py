"""Run QA -> clean -> gaps -> align on one source's daily series and emit Data Journey payloads. Owner: M3."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pandas as pd

from ftm.contracts.models import (
    JourneyStage,
    JourneyStageName,
    ProcessingRun,
    QualityFlag,
    StageStatus,
    ValueKind,
)
from ftm.data.pipeline.align import align_daily
from ftm.data.pipeline.clean import clean
from ftm.data.pipeline.gaps import DEFAULT_MAX_GAP_DAYS, handle_gaps
from ftm.data.pipeline.qa import check
from ftm.provenance import new_id

PIPELINE_VERSION = "0.2.0"  # 0.2.0: align step added
SAMPLE_DAYS = 60  # raw-vs-clean chart sample, keeps payloads small


@dataclass(frozen=True)
class AlignContext:
    """What the align step needs to know about the site and the source's own day and grid."""

    timezone: str  # site IANA timezone, e.g. "America/Chicago"
    source_time_standard: str | None  # e.g. POWER header "LST"
    native_resolution: str | None
    grid_point: tuple[float, float] | None  # (lon, lat) the source reports


@dataclass
class PipelineResult:
    observations: pd.DataFrame
    run: ProcessingRun
    gaps: list[dict[str, object]]
    journey: list[JourneyStage] = field(default_factory=list)


def run_daily_pipeline(
    obs: pd.DataFrame,
    *,
    site_id: str,
    source_id: str,
    fill_value: float,
    start: date,
    end: date,
    value_kind: ValueKind,
    align: AlignContext,
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
    is_demo: bool = False,
) -> PipelineResult:
    raw_before = obs["raw_value"].copy()
    df, qa_step = check(obs, fill_value=fill_value, start=start, end=end, value_kind=value_kind)
    df, clean_step = clean(df)
    df, gap_step, gaps = handle_gaps(df, max_gap_days=max_gap_days)
    df, align_step = align_daily(
        df,
        timezone=align.timezone,
        source_time_standard=align.source_time_standard,
        native_resolution=align.native_resolution,
        grid_point=align.grid_point,
    )

    # Guard the core rule: raw values delivered by the source are never modified.
    delivered = df[df["flag_reason"] != "not delivered by source"]["raw_value"]
    if sorted(delivered.dropna().tolist()) != sorted(raw_before.dropna().tolist()):
        raise AssertionError("pipeline modified raw values")

    run_id = new_id("proc")
    df["processing_run_id"] = run_id
    df["source_id"] = source_id
    df["site_id"] = site_id
    flags = df["quality_flag"].value_counts().to_dict()
    run = ProcessingRun(
        id=run_id,
        version=PIPELINE_VERSION,
        site_id=site_id,
        input_source_ids=[source_id],
        steps=[qa_step, clean_step, gap_step, align_step],
        created_at=datetime.now(UTC),
        summary={"rows": len(df), "flag_counts": {str(k): int(v) for k, v in flags.items()}},
    )
    result = PipelineResult(observations=df, run=run, gaps=gaps)
    result.journey = _journey(result, source_id, is_demo)
    return result


def _journey(res: PipelineResult, source_id: str, is_demo: bool) -> list[JourneyStage]:
    df, run = res.observations, res.run
    qa_step, clean_step, gap_step, align_step = run.steps
    per_var = qa_step.params["per_variable"]
    counts = {f.value: int((df["quality_flag"] == f.value).sum()) for f in QualityFlag}
    common = {"source_ids": [source_id], "processing_run_id": run.id, "is_demo": is_demo}

    # Counts come from each step's own record: later steps change flags (a rejected value can become
    # ESTIMATED), so final flag counts would misreport what Check and Clean actually found.
    missing = sum(v["missing"] for v in per_var.values())
    check_stage = JourneyStage(
        stage=JourneyStageName.CHECK,
        status=StageStatus.WARNING if missing or counts[QualityFlag.DUPLICATE.value] else StageStatus.OK,
        summary=(
            f"{sum(v['received'] for v in per_var.values())} values received of "
            f"{sum(v['expected'] for v in per_var.values())} expected; {missing} missing, "
            f"{counts[QualityFlag.DUPLICATE.value]} duplicate."
        ),
        chart={"type": "missing_timeline", "series": _missing_timeline(df)},
        details={"per_variable": per_var, "conflicting_duplicates": qa_step.params["conflicting_duplicates"]},
        **common,
    )

    rejected = sum(clean_step.params["rejected_per_variable"].values())
    clean_stage = JourneyStage(
        stage=JourneyStageName.CLEAN,
        status=StageStatus.WARNING if rejected or counts[QualityFlag.FLAGGED.value] else StageStatus.OK,
        summary=(
            f"{rejected} impossible values rejected, {counts[QualityFlag.FLAGGED.value]} flagged; "
            "no unit conversion was needed."
        ),
        chart={"type": "raw_vs_clean", "series": _raw_vs_clean(df)},
        details=clean_step.params,
        **common,
    )

    unresolved = [g for g in res.gaps if not g["resolved"]]
    gaps_stage = JourneyStage(
        stage=JourneyStageName.HANDLE_GAPS,
        status=StageStatus.WARNING if unresolved else StageStatus.OK,
        summary=(
            f"{gap_step.affected_count} values estimated in short gaps; {len(unresolved)} gaps left "
            "unresolved (rainfall gaps are never filled)."
        ),
        chart={"type": "gap_markers", "gaps": res.gaps},
        details=gap_step.params,
        **common,
    )
    ap = align_step.params
    align_stage = JourneyStage(
        stage=JourneyStageName.ALIGN,
        status=StageStatus.OK,
        summary=(
            f"Daily values stamped in {ap['timezone']}; source day = {ap['source_day_definition']}; "
            f"native resolution kept ({ap['native_resolution'] or 'not stated'}), nothing resampled."
        ),
        chart={"type": "footprint", "grid_point_lon_lat": ap["grid_point_lon_lat"]},
        details=ap,
        **common,
    )
    return [check_stage, clean_stage, gaps_stage, align_stage]


def _missing_timeline(df: pd.DataFrame) -> dict[str, list[str]]:
    bad = df[df["quality_flag"].isin([QualityFlag.MISSING.value, QualityFlag.ESTIMATED.value])]
    return {str(v): sorted(d.isoformat() for d in g["date"]) for v, g in bad.groupby("variable")}


def _raw_vs_clean(df: pd.DataFrame) -> dict[str, list[dict[str, object]]]:
    out: dict[str, list[dict[str, object]]] = {}
    primary = df[df["quality_flag"] != QualityFlag.DUPLICATE.value]
    for var, g in primary.groupby("variable"):
        tail = g.sort_values("date").tail(SAMPLE_DAYS)
        out[str(var)] = [
            {
                "date": r.date.isoformat(),
                "raw": None if pd.isna(r.raw_value) else float(r.raw_value),
                "processed": None if pd.isna(r.processed_value) else float(r.processed_value),
                "flag": r.quality_flag,
            }
            for r in tail.itertuples()
        ]
    return out

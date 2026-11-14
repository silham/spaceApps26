"""Validate-stage payload for the Data Journey, built from stored Validation records. Owner: M5.

Shows what was actually evaluated, with sample counts and failures, and says plainly what has not been
evaluated (held-out test years, weather coverage before the M4 ensemble exists). No accuracy claim is made
beyond the stored metrics.
"""

from __future__ import annotations

from ftm.contracts.models import JourneyStage, JourneyStageName, StageStatus, Validation

NOT_YET = (
    "Held-out test years (2020-2025) are not evaluated until feature freeze.",
    "Weather-range coverage is not evaluated yet: it needs the simulation ensemble (M4).",
)


def validate_stage(
    records: list[Validation], *, source_ids: list[str] | None = None, is_demo: bool = False
) -> JourneyStage:
    if not records:
        return JourneyStage(
            stage=JourneyStageName.VALIDATE,
            status=StageStatus.NOT_STARTED,
            summary="No validation has been run for this site yet.",
            source_ids=source_ids or [],
            details={"not_yet_evaluated": list(NOT_YET)},
            is_demo=is_demo,
        )
    r = records[0]  # newest first
    m = r.metrics
    n_t, n_d = int(m.get("tuning_n", 0)), int(m.get("dev_n", 0))
    found = round(m.get("tuning_detection_rate", 0) * n_t)
    bias = m.get("tuning_bias_days", float("nan"))
    summary = (
        f"Season starts checked against {r.reference.split(',')[0]}: found {found} of {n_t} tuning seasons; "
        f"detected green-up is on average {bias:+.0f} days after the statewide planting date. "
        f"Development check: n = {n_d}."
    )
    years = sorted({int(k.rsplit("_", 1)[1]) for k in m if k.startswith("ref_doy_")})
    chart = {
        "type": "observed_vs_detected",
        "x": "year",
        "y_unit": "day of year",
        "points": [
            {
                "year": y,
                "reference_doy": m.get(f"ref_doy_{y}"),
                "detected_doy": m.get(f"det_doy_{y}"),
                "split": "tuning" if y <= 2014 else "development",
            }
            for y in years
        ],
    }
    return JourneyStage(
        stage=JourneyStageName.VALIDATE,
        status=StageStatus.WARNING if r.failures else StageStatus.OK,
        summary=summary,
        source_ids=source_ids or [],
        chart=chart,
        details={
            "validation_id": r.id,
            "target": r.target,
            "reference": r.reference,
            "calibration_period": [d.isoformat() for d in r.calibration_period] if r.calibration_period else None,
            "test_period": None,
            "sample_count": r.sample_count,
            "metrics": {k: v for k, v in m.items() if not k.startswith(("ref_doy_", "det_doy_"))},
            "failures": r.failures,
            "independence_notes": r.independence_notes,
            "not_yet_evaluated": list(NOT_YET),
        },
        is_demo=is_demo,
    )

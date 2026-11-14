"""Suggested rotations as a background job (D16). Owner: M1 (method: ``ftm.engine.recommend``, M4).

Jobs live in this server process (like farm loads): a restart forgets them and the farmer simply asks again. Each
job stores its request, seed, horizon and sources so the result can be reproduced.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import numpy as np
from sqlalchemy.orm import Session

from ftm.api.services.prediction import prediction_for
from ftm.api.services.rotations import active_strategies, selectable_crops
from ftm.api.services.runs import farmer_context_for
from ftm.contracts.models import (
    CandidateMetric,
    RecommendationJob,
    RecommendationRequest,
    RotationCandidate,
)
from ftm.data.engine_inputs import DEFAULT_POOL
from ftm.db.session import get_engine
from ftm.engine.ensemble import SoilRunConfig, metric_unit, usable_blocks
from ftm.engine.params import LITERATURE_SOURCES
from ftm.engine.recommend import ASSUMPTIONS, Constraints, Evaluated, eligible_crops, suggest
from ftm.engine.yield_response import REL_YIELD_PREFIX
from ftm.provenance import new_id

SEED = 20261115
METRICS = (
    "possible_low_cover_days",
    "cover_days",
    "irrigation_mm",
    "water_stress_days",
    "runoff_mm",
    "deep_drainage_mm",
)
LABEL = {"cover": "possible low-cover days", "irrigation": "irrigation", "soil_health": "soil-health rules met"}

_lock = threading.Lock()
_jobs: dict[str, RecommendationJob] = {}
_one = threading.Semaphore(1)  # one suggestion search at a time: it is CPU-bound


class RecommendationError(ValueError):
    pass


def start(session: Session, site_id: str, req: RecommendationRequest) -> RecommendationJob:
    crops = selectable_crops()
    bad = sorted({*req.exclude_crop_ids, *([req.require_crop_id] if req.require_crop_id else [])} - set(crops))
    if bad:
        raise RecommendationError(f"unknown crop id(s) {bad}; known: {sorted(crops)}")
    if req.require_crop_id and req.require_crop_id in req.exclude_crop_ids:
        raise RecommendationError("a crop cannot be both required and excluded")
    job = RecommendationJob(
        id=new_id("rec"), site_id=site_id, status="queued", progress=0.0, request=req, created_at=datetime.now(UTC)
    )
    with _lock:
        _jobs[job.id] = job
    threading.Thread(target=_run, args=(job.id,), name=f"suggest-{site_id}", daemon=True).start()
    return job


def get(job_id: str, site_id: str) -> RecommendationJob:
    with _lock:
        job = _jobs.get(job_id)
    if job is None or job.site_id != site_id:
        raise LookupError(f"suggestion {job_id!r} not found (they are kept until the server restarts)")
    return job


def _set(job_id: str, **changes: object) -> None:
    with _lock:
        _jobs[job_id] = _jobs[job_id].model_copy(update=changes)


def _run(job_id: str) -> None:
    with _one, Session(get_engine()) as session:
        try:
            _set(job_id, status="running", message="Preparing the prediction")
            _compute(session, job_id)
        except Exception as exc:  # shown to the farmer; the job ends instead of hanging
            _set(job_id, status="failed", message=str(exc)[:500], finished_at=datetime.now(UTC))


def _compute(session: Session, job_id: str) -> None:
    job = get(job_id, _jobs[job_id].site_id)
    req, site_id = job.request, job.site_id
    crops = selectable_crops()
    pred, inputs, et0 = prediction_for(session, site_id, crops)
    ctx = farmer_context_for(session, site_id)
    available = frozenset(ctx.available_crop_ids) if ctx and ctx.available_crop_ids is not None else None
    c = Constraints(
        priorities=tuple(req.priorities),  # type: ignore[arg-type]
        irrigation_allowed=req.irrigation_allowed,
        max_irrigation_mm=req.max_irrigation_mm,
        exclude=frozenset(req.exclude_crop_ids),
        require=req.require_crop_id,
        max_seasons=req.max_seasons,
        min_relative_yield_pct=req.min_relative_yield_pct,
        available=available,
        southern_hemisphere=inputs.site.latitude < 0,
    )
    current = next((s for s in active_strategies(session, site_id) if s.is_baseline), None)
    if current is not None and (
        not current.seasons
        or min(x.plant_date for x in current.seasons) < pred.horizon[0]
        or max(x.end_date for x in current.seasons) > pred.horizon[1]
        or (current.feasibility is not None and not current.feasibility.feasible)
    ):
        current = None  # infeasible, or saved before the horizon moved: not comparable until fixed
    pool = usable_blocks(inputs.forcing, et0, pred.horizon[0].strftime("%m-%d"), DEFAULT_POOL)
    config = SoilRunConfig(soil=inputs.soil, initial_fraction=pred.initial.fraction, warmup=False)
    result = suggest(
        inputs.forcing,
        et0,
        pool,
        crops,
        config,
        c,
        site_id=site_id,
        horizon=pred.horizon,
        first_block_weights=pred.weights.as_dict() if pred.weights else None,
        seed=SEED,
        standing=pred.standing,
        current=current,
        progress=lambda f, m: _set(job_id, progress=round(min(f, 1.0), 3), message=m),
    )
    cur = _candidate(result.current, None, None, req, crops) if result.current else None
    best = result.ranked[0] if result.ranked else None
    candidates = [_candidate(e, k + 1, best, req, crops, result.current) for k, e in enumerate(result.ranked)]
    sources = [inputs.weather_source.id, *([pred.forecast_source_id] if pred.forecast_source_id else [])]
    sources += [*inputs.soil_profile.source_ids, *(s.id for s in LITERATURE_SOURCES)]
    _set(
        job_id,
        status="done",
        progress=1.0,
        message=None
        if candidates
        else "No rotation met your constraints; try a lower yield floor or allow irrigation.",
        finished_at=datetime.now(UTC),
        horizon_start=pred.horizon[0],
        horizon_end=pred.horizon[1],
        candidates_considered=result.considered,
        candidates=candidates,
        current_practice=cur,
        n_paths=result.stage2_paths,
        source_ids=list(dict.fromkeys(sources)),
        assumptions=[
            *ASSUMPTIONS,
            *_left_out(crops, c),
            *_tropics(inputs.site.latitude),
            pred.initial.assumption,
            *pred.notes,
            *_standing_note(pred, crops),
        ],
        limitations=[
            "Suggestions are ordered by your priorities among options the model found; they are not the only good "
            "rotations, and local knowledge (markets, equipment, pests) is not in the model.",
            "Crop parameters are generic FAO table values, not calibrated to your field. Soil-health rules are "
            "conditional rules of thumb, not measured soil gains.",
            "Past NASA POWER years are resampled, weighted by the seasonal forecast; no day is a weather forecast.",
            "Irrigation is net (100% efficiency) under the refill rule; frost damage is not modelled.",
        ],
    )


def _left_out(crops, c: Constraints) -> list[str]:  # type: ignore[no-untyped-def]
    """Which catalog crops can never appear in these suggestions, and why (never silently)."""
    used = eligible_crops(crops, c)
    out = []
    for cid, e in sorted(crops.items()):
        if cid in used:
            continue
        p = e.profile
        why = (
            "excluded by you or not among the crops you can grow"
            if cid in c.exclude or (c.available is not None and cid not in c.available)
            else "no cited base temperature or FAO-56 Table 11 planting month"
            if p.t_base_c is None or p.t_base_c.value is None or not p.table11_planting_months
            else "no seasonal Ky, so its yield cannot be checked against your floor"
        )
        out.append(f"{p.name} is not suggested: {why}.")
    return out


def _tropics(latitude: float) -> list[str]:
    if abs(latitude) >= 23.5:
        return []
    return [
        "This farm is in the tropics: planting months follow FAO-56 Table 11 rows from mid-latitudes (shifted six "
        "months south of the equator), which may not match rainy-season planting here."
    ]


def _standing_note(pred, crops) -> list[str]:  # type: ignore[no-untyped-def]
    st = pred.standing
    if st is None:
        return []
    return [
        f"Every option starts after the crop on the field now ({crops[st.crop_id].profile.name}) is harvested "
        f"on {st.end_date}."
    ]


def _pct(values: list[float]) -> tuple[float | None, float | None, float | None]:
    arr = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if arr.size == 0:
        return None, None, None
    p10, p50, p90 = np.percentile(arr, [10, 50, 90])
    return round(float(p10), 1), round(float(p50), 1), round(float(p90), 1)


def _metrics(e: Evaluated, current: Evaluated | None) -> list[CandidateMetric]:
    keys = [*METRICS, *sorted(k for k in e.per_path[0] if k.startswith(REL_YIELD_PREFIX))] if e.per_path else []
    out = []
    for k in keys:
        vals = [p.get(k, float("nan")) for p in e.per_path]
        p10, p50, p90 = _pct(vals)
        delta = None
        if current is not None and k in METRICS:  # same paths in the same order: per-path differences (D12)
            d = [a - b.get(k, float("nan")) for a, b in zip(vals, current.per_path, strict=True)]
            delta = _pct(d)[1]
        season = int(k[len(REL_YIELD_PREFIX) :]) if k.startswith(REL_YIELD_PREFIX) else None
        out.append(
            CandidateMetric(
                metric="relative_yield_pct" if season is not None else k,
                unit=metric_unit(k),
                season_index=season,
                p10=p10,
                p50=p50,
                p90=p90,
                delta_p50_vs_current=delta,
            )
        )
    return out


def _fmt(obj: str, v: float) -> str:
    return f"{v:.0f} days" if obj == "cover" else (f"{v:.0f} mm" if obj == "irrigation" else f"{v:.0f} of 3")


def _candidate(
    e: Evaluated,
    rank: int | None,
    best: Evaluated | None,
    req: RecommendationRequest,
    crops,  # type: ignore[no-untyped-def]
    current: Evaluated | None = None,
) -> RotationCandidate:
    o = e.objectives
    why: list[str] = []
    trade: list[str] = []
    if rank is not None:
        why.append(f"Rank {rank} in your order: " + ", then ".join(LABEL[p] for p in req.priorities) + ".")
        why += [
            f"{LABEL[p].capitalize()}: {_fmt(p, o[p])}{'' if p == 'soil_health' else ' (median)'}."
            for p in req.priorities
        ]
        if best is not None and best is not e:
            for p in req.priorities:
                worse = o[p] - best.objectives[p]
                if (p == "soil_health" and worse < 0) or (p != "soil_health" and worse > 0):
                    trade.append(
                        f"{LABEL[p].capitalize()}: "
                        f"{f'{abs(worse):.0f} fewer' if p == 'soil_health' else f'{_fmt(p, abs(worse))} more'} "
                        "than option 1."
                    )
        if current is not None:
            for p in ("cover", "irrigation"):
                # D12: median of per-path differences (same paths), as on the metric line; not a difference of medians
                key = "possible_low_cover_days" if p == "cover" else "irrigation_mm"
                pairs = zip(e.per_path, current.per_path, strict=True)
                diffs = [a.get(key, np.nan) - b.get(key, np.nan) for a, b in pairs]
                d = _pct(diffs)[1]
                if d is not None and abs(d) >= 1:
                    trade.append(
                        f"{LABEL[p].capitalize()}: {_fmt(p, abs(d))} {'more' if d > 0 else 'less'} "
                        "than your current practice."
                    )
        irrigated = [crops[s.crop_id].profile.name for s in e.strategy.seasons if s.irrigation_rule and s.crop_id]
        if irrigated:
            why.append(
                f"Irrigated only where needed to reach {req.min_relative_yield_pct:g}% relative yield: "
                f"{', '.join(irrigated)}."
            )
    return RotationCandidate(
        rank=rank,
        name=e.strategy.name,
        seasons=e.strategy.seasons,
        metrics=_metrics(e, current),
        soil_health=e.soil,
        soil_rules_met=int(o.get("soil_health", 0)),
        non_dominated=rank is not None,
        why=why,
        trade_offs=trade,
    )

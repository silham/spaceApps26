"""Save a farm's user-built rotations (D15). Owner: M1 (engine parameters: M4).

Strategy ids are ``rot<position>_<hash>``, so the saved order (current practice first) survives a reload.

A rotation is a list of seasons the farmer chose: crop, planting date, rainfed or irrigated. The harvest date is
computed from the crop's FAO-56 stage lengths. Rotation 1 is current practice (the baseline). Saving replaces the
farm's active rotations; the old rows are marked superseded, not deleted, because earlier results reference them.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.services.runs import farmer_context_for
from ftm.contracts.models import Feasibility, RotationsUpdate, SeasonPlan, Strategy
from ftm.data.engine_inputs import SOIL_DATA_DEPTH_M, latest_soil_profile
from ftm.db.models import SiteRow, StrategyRow
from ftm.engine.params import CatalogError, CropEntry, load_crops, soil_spec_from_profile
from ftm.engine.rotation import SUPPORTED_IRRIGATION_RULE, check_feasibility
from ftm.engine.scenarios import _end
from ftm.provenance import inputs_hash


class RotationError(ValueError):
    """The submitted rotations cannot be saved; the message is readable by the farmer."""


def selectable_crops() -> dict[str, CropEntry]:
    return load_crops()


def _season(entry: CropEntry, plant, irrigated: bool, usual: float | None) -> SeasonPlan:  # type: ignore[no-untyped-def]
    end = _end(entry, plant)
    if end is None:
        raise RotationError(f"{entry.profile.name} has no complete growth-stage lengths in the crop catalog")
    return SeasonPlan(
        crop_id=entry.profile.id,
        plant_date=plant,
        end_date=end,
        irrigation_rule=SUPPORTED_IRRIGATION_RULE if irrigated else None,
        usual_yield_t_ha=usual,
    )


def comparison_horizon(session: Session, site_id: str) -> tuple[date, date]:
    """D16: the real-calendar horizon, from the day after the last observed weather day, 24 months."""
    from ftm.api.services.prediction import horizon_for
    from ftm.data.engine_inputs import EngineInputsNotAvailableError

    try:
        h = horizon_for(session, site_id)
    except (EngineInputsNotAvailableError, ValueError) as exc:
        raise RotationError(f"the farm's weather is not ready, so the comparison period is unknown: {exc}") from exc
    return h.start, h.end


def build_strategies(session: Session, site: SiteRow, req: RotationsUpdate) -> list[Strategy]:
    crops = selectable_crops()
    horizon = comparison_horizon(session, site.id)
    ctx = farmer_context_for(session, site.id)
    allowed = set(ctx.available_crop_ids) if ctx and ctx.available_crop_ids is not None else None
    strategies: list[Strategy] = []
    for i, rotation in enumerate(req.rotations):
        seasons: list[SeasonPlan] = []
        for j, s in enumerate(rotation.seasons):
            where = f"Rotation {i + 1} ({rotation.name}), season {j + 1}"
            if s.crop_id not in crops:
                raise RotationError(f"{where}: unknown crop {s.crop_id!r}; choose one of {sorted(crops)}")
            if allowed is not None and s.crop_id not in allowed:
                raise RotationError(f"{where}: {s.crop_id!r} is not among the crops you said you can grow")
            if not horizon[0] <= s.plant_date <= horizon[1]:
                raise RotationError(
                    f"{where}: planting date {s.plant_date} is outside the comparison period "
                    f"{horizon[0]} to {horizon[1]}"
                )
            seasons.append(_season(crops[s.crop_id], s.plant_date, s.irrigated, s.usual_yield_t_ha))
        key = inputs_hash(
            {
                "site": site.id,
                "i": i,
                "name": rotation.name,
                "seasons": [s.model_dump(mode="json") for s in seasons],
            }
        )
        strategies.append(
            Strategy(id=f"rot{i}_{key[:12]}", site_id=site.id, name=rotation.name, is_baseline=i == 0, seasons=seasons)
        )
    return strategies


def _soil_or_none(session: Session, site_id: str):  # type: ignore[no-untyped-def]
    row = latest_soil_profile(session, site_id)
    if row is None:
        return None
    from ftm.contracts.models import SoilProfile

    try:
        return soil_spec_from_profile(SoilProfile.model_validate(row.params), data_depth_m=SOIL_DATA_DEPTH_M)
    except CatalogError:
        return None  # the run reports the unsupported texture; feasibility is then unknown until it runs


def _after_standing_crop(session: Session, site_id: str, s: Strategy, crops: dict[str, CropEntry]) -> Strategy:
    """D16: a season cannot be planted before the crop the farmer reports on the field now is harvested."""
    from ftm.api.services.prediction import prediction_for

    st = prediction_for(session, site_id, crops)[0].standing
    early = [x for x in s.seasons if st is not None and x.plant_date <= st.end_date]
    if st is None or not early:
        return s
    name = crops[st.crop_id].profile.name if st.crop_id in crops else st.crop_id
    prior = s.feasibility.reasons if s.feasibility else []
    reasons = [
        *prior,
        *(
            f"Season planted {x.plant_date} starts before the crop on the field now ({name}) is harvested on "
            f"{st.end_date}."
            for x in early
        ),
    ]
    return s.model_copy(update={"feasibility": Feasibility(feasible=False, reasons=reasons)})


def save_rotations(session: Session, site: SiteRow, req: RotationsUpdate) -> list[Strategy]:
    strategies = build_strategies(session, site, req)
    horizon = comparison_horizon(session, site.id)
    crops = selectable_crops()
    ctx = farmer_context_for(session, site.id)
    allowed = set(ctx.available_crop_ids) if ctx and ctx.available_crop_ids is not None else None
    soil = _soil_or_none(session, site.id)
    if soil is not None:
        strategies = [
            s.model_copy(
                update={
                    "feasibility": check_feasibility(s, crops, horizon=horizon, soil=soil, available_crop_ids=allowed)
                }
            )
            for s in strategies
        ]
    strategies = [_after_standing_crop(session, site.id, s, crops) for s in strategies]
    keep = {s.id for s in strategies}
    for old in session.scalars(
        select(StrategyRow).where(StrategyRow.site_id == site.id, StrategyRow.superseded.is_(False))
    ):
        if old.id not in keep:
            old.superseded = True
    for s in strategies:
        data = s.model_dump(mode="json")
        row = session.get(StrategyRow, s.id)
        if row is None:
            session.add(StrategyRow(**data))
        else:
            row.name, row.is_baseline = data["name"], data["is_baseline"]
            row.seasons, row.feasibility, row.superseded = data["seasons"], data["feasibility"], False
    session.commit()
    return strategies


def active_strategies(session: Session, site_id: str) -> list[Strategy]:
    rows = session.scalars(
        select(StrategyRow)
        .where(StrategyRow.site_id == site_id, StrategyRow.superseded.is_(False))
        .order_by(StrategyRow.is_baseline.desc(), StrategyRow.created_at, StrategyRow.id)
    )
    return [Strategy.model_validate(r) for r in rows]

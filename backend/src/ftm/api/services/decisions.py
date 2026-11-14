"""Decision cards: the farmer's choice and reason, frozen with the evidence it rests on. Owner: M1.

DEVELOPMENT_GUIDE section 4 "Decide" and section 11 item 12: the export carries the sources actually used,
the run and model versions, parameters, ranges, assumptions, limitations and local-review questions. A card
is refused for an infeasible strategy or a run without stored detail. JSON is the record; the PDF is a
rendering of the same content (reportlab, BSD licence).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.services import runs as run_svc
from ftm.config import get_settings
from ftm.contracts.models import (
    RANGE_LABEL,
    CropProfile,
    DecisionCard,
    DecisionCardRequest,
    PairedDelta,
    Result,
    RunDetail,
    SimulationMode,
    Source,
    Strategy,
)
from ftm.data.engine_inputs import source_contract
from ftm.db.models import DecisionRecordRow, SiteRow, SoilProfileRow, SourceRow
from ftm.engine.params import load_crops, load_local_crops
from ftm.provenance import new_id, sha256_bytes

METRIC_LABELS = {
    "irrigation_mm": "Irrigation need (net)",
    "allocation_shortfall_days": "Days irrigation was short of the rule",
    "water_stress_days": "Water-stress days (model)",
    "aet_mm": "Actual evapotranspiration",
    "deep_drainage_mm": "Deep drainage",
    "runoff_mm": "Runoff",
    "cover_days": "Crop cover days",
    "possible_low_cover_days": "Possible low-cover days",
    "crop_diversity_count": "Distinct crops",
}


class DecisionRefusedError(ValueError):
    pass


class DecisionNotFoundError(LookupError):
    pass


def exports_dir() -> Path:
    path = get_settings().exports_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def catalog_crops() -> dict[str, CropProfile]:
    return {cid: e.profile for cid, e in {**load_crops(), **load_local_crops()}.items()}


def _season_text(st: Strategy, crops: dict[str, CropProfile]) -> str:
    parts = []
    for s in st.seasons:
        name = crops[s.crop_id].name if s.crop_id in crops else (s.crop_id or "fallow")
        water = "irrigated" if s.irrigation_rule else "rainfed"
        parts.append(f"{name} ({water}) {s.plant_date:%d %b %Y} – {s.end_date:%d %b %Y}")
    return "; ".join(parts)


def _assumptions(detail: RunDetail, crops: dict[str, CropProfile]) -> list[str]:
    run, req = detail.run, detail.request
    out = [
        f"Comparison horizon {run.input_versions.get('horizon', '')}; {run.n_paths} weather paths "
        f"({run.resampling_method}) from the sample pool {run.input_versions.get('sample_pool', '')}, seed {run.seed}.",
        f"Weather: one source per run ({run.weather_source_id}); processing run "
        f"{run.input_versions.get('weather_processing_run_id')}.",
        f"Soil profile {run.input_versions.get('soil_profile_id')}; initial soil water "
        f"{run.input_versions.get('initial_fraction_of_field_capacity')} of field capacity before warm-up.",
        (
            f"Irrigation mode: fixed allocation of {run.allocation_mm:g} mm per irrigated season (never exceeded)."
            if run.mode is SimulationMode.FIXED_ALLOCATION and run.allocation_mm is not None
            else "Irrigation mode: irrigation as needed under the stated refill rule (net, 100% efficiency)."
        ),
    ]
    shifts = {k: v for k, v in req.planting_shift_days.items() if v}
    if shifts:
        out.append("Planting shifts applied: " + ", ".join(f"{k} {v:+d} days" for k, v in shifts.items()) + ".")
    out += [f"{st.name}: {_season_text(st, crops)}." for st in detail.strategies]
    out += detail.scenario_notes
    used = {s.crop_id for st in detail.strategies for s in st.seasons if s.crop_id}
    for cid in sorted(used):
        c = crops.get(cid)
        if c is None:
            continue
        stages = "/".join(f"{int(v.value)}" if v.value is not None else "?" for v in c.stage_lengths_days.values())
        out.append(
            f"{c.name}: Kc {c.kc_ini.value}/{c.kc_mid.value}/{c.kc_end.value} ({c.kc_mid.reference}); "
            f"stages {stages} d ({c.stage_lengths_days['ini'].reference}); root depth {c.max_root_depth_m.value} m; "
            f"p {c.depletion_fraction_p.value}."
        )
    return out


def _questions(session: Session, detail: RunDetail, crops: dict[str, CropProfile]) -> list[str]:
    """Questions for local review, built only from what this run used (no site-specific text)."""
    q = []
    seen: set[tuple[str, date]] = set()
    dates = []
    for st in detail.strategies:
        for s in st.seasons:
            if s.crop_id and (s.crop_id, s.plant_date) not in seen:
                seen.add((s.crop_id, s.plant_date))
                name = crops[s.crop_id].name if s.crop_id in crops else s.crop_id
                dates.append(f"{name} {s.plant_date:%d %b}")
    if dates:
        how = " ".join(detail.scenario_notes) or "see the run's scenario notes"
        q.append(
            "Are these planting dates realistic for this field? "
            + ", ".join(dates)
            + f". They are model choices, not farm records. How they were set: {how}"
        )
    if any(s.irrigation_rule for st in detail.strategies for s in st.seasons):
        q.append(
            "What irrigation allocation per season does the water right or well capacity allow, and what is the "
            "system's application efficiency? The model counts net irrigation at 100% efficiency."
        )
    soil = session.get(SoilProfileRow, detail.run.input_versions.get("soil_profile_id", ""))
    if soil is not None:
        awc = soil.params.get("available_water_capacity_mm_per_m", {}).get("value")
        q.append(
            f"Does the soil match the stored profile ({soil.params.get('texture') or 'texture unknown'}, "
            f"available water {awc} mm/m over the top 1 m)? A local soil test would replace this value."
        )
    used = sorted({s.crop_id for st in detail.strategies for s in st.seasons if s.crop_id})
    names = [crops[c].name if c in crops else c for c in used]
    q.append(f"Can every crop in these options be grown, sold or used on this farm? ({', '.join(names)})")
    q.append("Which equipment (planter, harvester, irrigation system) constraints would rule out any of these seasons?")
    return q


def create_card(session: Session, req: DecisionCardRequest) -> DecisionCard:
    row = run_svc.get_run_row(session, req.run_id)
    detail = run_svc.detail_from_row(row)
    if detail.run.site_id != req.site_id:
        raise DecisionRefusedError(f"run {req.run_id!r} belongs to site {detail.run.site_id!r}, not {req.site_id!r}")
    chosen = next((s for s in detail.strategies if s.id == req.chosen_strategy_id), None)
    if chosen is None:
        raise DecisionRefusedError(f"strategy {req.chosen_strategy_id!r} is not part of run {req.run_id!r}")
    if chosen.feasibility is not None and not chosen.feasibility.feasible:
        raise DecisionRefusedError(f"{chosen.name} is infeasible in this run: " + "; ".join(chosen.feasibility.reasons))
    site = session.get(SiteRow, req.site_id)
    assert site is not None
    results: list[Result] = run_svc.get_results(session, req.run_id)
    deltas: list[PairedDelta] = run_svc.get_deltas(session, req.run_id)
    src_rows = session.scalars(select(SourceRow).where(SourceRow.id.in_(detail.source_ids))).all()
    sources: list[Source] = [source_contract(r) for r in src_rows]
    crops = catalog_crops()
    used = sorted({s.crop_id for st in detail.strategies for s in st.seasons if s.crop_id})
    card_id = new_id("card")
    farmer = run_svc._farmer_context(session, req.site_id)
    card = DecisionCard(
        id=card_id,
        site_id=req.site_id,
        site_name=site.name,
        created_at=datetime.now(UTC),
        chosen_strategy_id=chosen.id,
        reason=req.reason.strip(),
        priorities=req.priorities,
        farmer_context=farmer,
        run=detail.run,
        request=detail.request,
        strategies=detail.strategies,
        results=results,
        deltas=deltas,
        sources=sources,
        crops=[crops[c] for c in used if c in crops],
        assumptions=_assumptions(detail, crops),
        limitations=detail.limitations,
        local_review_questions=_questions(session, detail, crops),
        unsupported_claims=detail.unsupported_claims,
        json_url=f"/decision-cards/{card_id}.json",
        pdf_url=f"/decision-cards/{card_id}.pdf",
        is_demo=detail.run.is_demo or site.is_demo,
    )
    out = exports_dir()
    raw = json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False).encode("utf-8")
    json_path = out / f"{card_id}.json"
    json_path.write_bytes(raw)
    digest = sha256_bytes(raw)
    pdf_path = out / f"{card_id}.pdf"
    render_pdf(card, pdf_path)
    card = card.model_copy(update={"sha256": digest})
    session.add(
        DecisionRecordRow(
            id=card_id,
            site_id=req.site_id,
            chosen_strategy_id=chosen.id,
            run_id=req.run_id,
            reason=card.reason,
            payload=card.model_dump(mode="json"),
            json_path=json_path.name,
            pdf_path=pdf_path.name,
            sha256=digest,
        )
    )
    session.commit()
    return card


def get_card(session: Session, card_id: str) -> tuple[DecisionCard, DecisionRecordRow]:
    row = session.get(DecisionRecordRow, card_id)
    if row is None or row.payload is None:
        raise DecisionNotFoundError(f"decision card {card_id!r} not found")
    return DecisionCard.model_validate(row.payload), row


def list_cards(session: Session, site_id: str) -> list[DecisionCard]:
    rows = session.scalars(
        select(DecisionRecordRow)
        .where(DecisionRecordRow.site_id == site_id, DecisionRecordRow.payload.is_not(None))
        .order_by(DecisionRecordRow.created_at.desc())
    )
    return [DecisionCard.model_validate(r.payload) for r in rows]


def _fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:,.0f}"


def render_pdf(card: DecisionCard, path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    body, h1, h2 = styles["BodyText"], styles["Title"], styles["Heading2"]
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)

    def p(text: str, style=body) -> Paragraph:  # type: ignore[no-untyped-def]
        return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)

    names = {s.id: s.name for s in card.strategies}
    story = [
        p(("DEMO — " if card.is_demo else "") + "Farm Time Machine decision card", h1),
        p(f"{card.site_name} ({card.site_id}) · {card.created_at:%d %b %Y %H:%M} UTC · card {card.id}"),
        p(
            f"Run {card.run.id} · model {card.run.model_version} · {card.run.n_paths} weather paths · "
            f"seed {card.run.seed} · sha256 {card.sha256 or 'see JSON'}",
            small,
        ),
        Spacer(1, 4 * mm),
        p("Chosen strategy", h2),
        p(names.get(card.chosen_strategy_id, card.chosen_strategy_id)),
        p("Farmer's reason", h2),
        p(card.reason),
    ]
    if card.priorities:
        story.append(
            p(
                f"Priorities: conserve water {card.priorities.conserve_water}/100, "
                f"protect soil {card.priorities.protect_soil}/100 (priorities rank options; they never override "
                "hard constraints).",
                small,
            )
        )
    story += [p(f"Outcomes: median with {RANGE_LABEL}", h2)]
    by = {(r.strategy_id, r.metric): r for r in card.results}
    metrics = list(dict.fromkeys(r.metric for r in card.results))
    head = [p("Metric", small), *[p(names.get(s.id, s.id), small) for s in card.strategies]]
    rows = [head]
    for m in metrics:
        row = [f"{METRIC_LABELS.get(m, m)} ({by[card.strategies[0].id, m].unit})"]
        for s in card.strategies:
            r = by.get((s.id, m))
            row.append("n/a" if r is None or r.p50 is None else f"{_fmt(r.p50)} ({_fmt(r.p10)}–{_fmt(r.p90)})")
        rows.append(row)
    table = Table(rows, repeatRows=1, colWidths=[55 * mm] + [40 * mm] * len(card.strategies))
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EFEA")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)
    chosen_deltas = [d for d in card.deltas if d.strategy_id == card.chosen_strategy_id]
    if chosen_deltas:
        story.append(p("Difference from current practice (same weather, per path)", h2))
        for d in chosen_deltas:
            share = "" if d.share_better is None else f"; better in {d.share_better:.0%} of paths"
            story.append(
                p(
                    f"{METRIC_LABELS.get(d.metric, d.metric)}: {d.p50:+,.0f} {d.unit} "
                    f"({_fmt(d.p10)} to {_fmt(d.p90)}){share}",
                    small,
                )
            )
    sections = [
        ("Questions to review locally", card.local_review_questions),
        ("Assumptions", card.assumptions),
        ("Limitations", card.limitations),
        ("Not estimated by this tool", card.unsupported_claims),
    ]
    for title, items in sections:
        story.append(p(title, h2))
        story += [p(f"• {x}", small) for x in items]
    story.append(p("Sources used", h2))
    for src in card.sources:
        story.append(
            p(
                f"• {src.id}: {src.provider} — {src.product} ({src.kind.value}); "
                f"{src.license or 'licence not recorded'}; {src.url or src.doi or ''}",
                small,
            )
        )
    story.append(Spacer(1, 4 * mm))
    story.append(
        p(
            "Historical weather is resampled: this is not a forecast. Ranges are a central 80% simulation range, "
            "not a prediction interval. No NASA endorsement is implied.",
            small,
        )
    )
    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Decision card {card.id}",
    ).build(story)

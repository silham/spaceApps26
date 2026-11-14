"""Soil-health indicators of a rotation (D16). Owner: M4.

Rules of thumb from crop-rotation planning, stated conditionally and never turned into numbers (guide §7: "describe
nitrogen-fixing potential and pest-cycle interruption conditionally; do not convert them into unsupported
numerical gains"). Source: Mohler, C.L. & Johnson, S.E. (eds.) (2009) Crop Rotation on Organic Farms: A Planning
Manual, SARE / NRAES-177. Crop families and legume status come from the catalog (each with a citation); a crop
without them makes a rule "unknown", never assumed.

Soil cover is not a rule here: it is a simulated metric (possible low-cover days, cover days) of every run.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import pairwise
from typing import Literal

from ftm.contracts.models import SeasonPlan, SoilRuleResult, Strategy
from ftm.engine.params import CropEntry

REFERENCE = (
    "Mohler & Johnson (eds., 2009) Crop Rotation on Organic Farms: A Planning Manual, SARE/NRAES-177: p. 1 (avoid "
    "successive crops in the same plant family) and p. 4 (general principles quoted from Magdoff & van Es 2000: "
    "follow a legume with a high nitrogen demanding crop; don't follow a crop with a closely related species)"
)
Status = Literal["met", "not_met", "unknown"]


def _crops(seasons: list[SeasonPlan], crops: Mapping[str, CropEntry]) -> list[CropEntry | None]:
    return [crops.get(s.crop_id) if s.crop_id else None for s in seasons]


def soil_rules(
    strategy: Strategy, crops: Mapping[str, CropEntry], *, before: SeasonPlan | None = None
) -> list[SoilRuleResult]:
    """Indicators for the strategy's crops in planting order; ``before`` is the crop on the field now (if any),
    which precedes the first season."""
    seasons = sorted((s for s in strategy.seasons if s.crop_id), key=lambda s: s.plant_date)
    seq = ([before] if before and before.crop_id else []) + seasons
    entries = _crops(seq, crops)
    names = [e.profile.name if e else (s.crop_id or "?") for e, s in zip(entries, seq, strict=True)]
    out: list[SoilRuleResult] = []

    # 1. Family change: the same family back to back lets its pests and diseases carry over.
    pairs = list(pairwise(entries))
    if not pairs:
        out.append(_r("family_change", "Crop families alternate", "unknown", "Only one crop: nothing follows it."))
    elif any(a is None or b is None or a.profile.family is None or b.profile.family is None for a, b in pairs):
        out.append(_r("family_change", "Crop families alternate", "unknown", "A crop has no cited family."))
    else:
        repeats = [
            f"{names[i]} then {names[i + 1]} ({a.profile.family})"
            for i, (a, b) in enumerate(pairs)
            if a and b and a.profile.family == b.profile.family
        ]
        out.append(
            _r(
                "family_change",
                "Crop families alternate",
                "not_met" if repeats else "met",
                (
                    "Same family back to back: " + "; ".join(repeats) + ". Pests and diseases of that family may "
                    "carry over."
                )
                if repeats
                else "Each crop follows one of another family, which can interrupt pest and disease cycles.",
            )
        )

    # 2. A legume ahead of a non-legume: possible nitrogen left for the next crop (not quantified).
    legumes = [e is not None and e.profile.legume for e in entries]
    unknown = any(e is None or e.profile.legume is None for e in entries)
    followed = [
        f"{names[i]} before {names[i + 1]}"
        for i in range(len(entries) - 1)
        if legumes[i] and entries[i + 1] is not None and entries[i + 1].profile.legume is False  # type: ignore[union-attr]
    ]
    if followed:
        out.append(
            _r(
                "legume_before_nonlegume",
                "A legume comes before a non-legume",
                "met",
                "; ".join(followed) + ": the legume may leave some nitrogen for the next crop (not quantified). "
                "The source advises following a legume with a nitrogen-demanding crop; crop nitrogen demand is not "
                "in the catalog, so any non-legume counts here.",
            )
        )
    elif unknown:
        out.append(
            _r(
                "legume_before_nonlegume",
                "A legume comes before a non-legume",
                "unknown",
                "A crop's legume status is not cited.",
            )
        )
    else:
        out.append(
            _r(
                "legume_before_nonlegume",
                "A legume comes before a non-legume",
                "not_met",
                "No legume is followed by another crop, so no nitrogen carry-over can be expected.",
            )
        )

    # 3. Diversity: more families in the rotation.
    fams = {e.profile.family for e in entries if e and e.profile.family}
    status: Status = (
        "unknown"
        if any(e is None or e.profile.family is None for e in entries)
        else ("met" if len(fams) >= 2 else "not_met")
    )
    out.append(
        _r(
            "family_diversity",
            "Two or more crop families",
            status,
            f"{len(fams)} famil{'y' if len(fams) == 1 else 'ies'}: {', '.join(sorted(fams)) or 'none cited'}.",
        )
    )
    return out


def rules_met(rules: list[SoilRuleResult]) -> int:
    return sum(r.status == "met" for r in rules)


def _r(rule_id: str, label: str, status: Status, explanation: str) -> SoilRuleResult:
    return SoilRuleResult(rule_id=rule_id, label=label, status=status, explanation=explanation, reference=REFERENCE)

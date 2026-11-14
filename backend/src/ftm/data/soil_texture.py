"""USDA soil texture class from sand, silt and clay percentages. Owner: M3.

Boundaries follow the USDA texture triangle (USDA Soil Survey Manual, Soil Science Division Staff 2017,
chapter 3; the same rules the NRCS texture-by-feel flow uses). Inputs are percentages of the fine earth fraction
and are expected to sum to about 100; a sum outside 95-105 is refused rather than renormalised.
"""

from __future__ import annotations

SUM_TOLERANCE = 5.0


def usda_texture_class(sand: float, silt: float, clay: float) -> str | None:
    """Name of the USDA texture class, or ``None`` when the percentages are not a usable composition."""
    parts = (sand, silt, clay)
    if any(p < 0 for p in parts) or abs(sum(parts) - 100.0) > SUM_TOLERANCE:
        return None
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 1.5 * clay >= 15 and silt + 2 * clay < 30:
        return "loamy sand"
    if (7 <= clay < 20 and sand > 52 and silt + 2 * clay >= 30) or (clay < 7 and silt < 50 and silt + 2 * clay >= 30):
        return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "silty clay loam"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 40 and silt >= 40:
        return "silty clay"
    if clay >= 40 and sand <= 45 and silt < 40:
        return "clay"
    return None

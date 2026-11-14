"""Pipeline step: gaps (Data Journey stage "Handle gaps"). Owner: M3.

Rules (DEVELOPMENT_GUIDE.md section 6):
- Missing rainfall is NOT zero and is not interpolated. Rain gaps are left unresolved and reported.
- Continuous variables: a gap may be estimated only if it is at most ``max_gap_days`` long and has a
  valid value on both sides. Method: linear interpolation in time. Estimated values are flagged.
- Longer gaps stay unresolved.
"""

from __future__ import annotations

import pandas as pd

from ftm.contracts.models import ProcessingStep, QualityFlag, ValueKind

DEFAULT_MAX_GAP_DAYS = 2
NEVER_FILL = frozenset({"PRECTOTCORR", "PRECTOT", "PRECTOTLAND"})
GAP_FLAGS = (QualityFlag.MISSING.value, QualityFlag.REJECTED.value)


def handle_gaps(
    df: pd.DataFrame, *, max_gap_days: int = DEFAULT_MAX_GAP_DAYS
) -> tuple[pd.DataFrame, ProcessingStep, list[dict[str, object]]]:
    """Return (observations, step, gap list). Duplicate rows are ignored when finding gaps."""
    if max_gap_days < 0:
        raise ValueError("max_gap_days must be >= 0")
    out = df.copy()
    method = f"linear_interpolation_max_{max_gap_days}d"
    gaps: list[dict[str, object]] = []
    estimated = 0

    primary = out[out["quality_flag"] != QualityFlag.DUPLICATE.value]
    for var, g in primary.groupby("variable", sort=True):
        g = g.sort_values("date")
        is_gap = g["quality_flag"].isin(GAP_FLAGS).to_numpy()
        run_id = (pd.Series(is_gap) != pd.Series(is_gap).shift()).cumsum().to_numpy()
        for rid in sorted(set(run_id[is_gap])):
            pos = [i for i in range(len(g)) if run_id[i] == rid]
            first, last = pos[0], pos[-1]
            length = len(pos)
            bounded = first > 0 and last < len(g) - 1
            fill = var not in NEVER_FILL and length <= max_gap_days and bounded
            if fill:
                before = g.iloc[first - 1]
                after = g.iloc[last + 1]
                span = (after["date"] - before["date"]).days
                for p in pos:
                    row = g.iloc[p]
                    frac = (row["date"] - before["date"]).days / span
                    value = before["processed_value"] + frac * (after["processed_value"] - before["processed_value"])
                    out.loc[g.index[p], ["processed_value", "quality_flag", "value_kind", "imputation_method"]] = [
                        value,
                        QualityFlag.ESTIMATED.value,
                        ValueKind.ESTIMATED.value,
                        method,
                    ]
                estimated += length
            gaps.append(
                {
                    "variable": var,
                    "start": g.iloc[first]["date"].isoformat(),
                    "end": g.iloc[last]["date"].isoformat(),
                    "length_days": length,
                    "resolved": fill,
                    "method": method if fill else None,
                    "why_unresolved": None if fill else _why(str(var), length, max_gap_days, bounded),
                }
            )

    step = ProcessingStep(
        name="handle_gaps",
        params={
            "max_gap_days": max_gap_days,
            "method": method,
            "never_filled": sorted(NEVER_FILL),
            "gaps_total": len(gaps),
            "gaps_resolved": sum(1 for g in gaps if g["resolved"]),
        },
        affected_count=estimated,
        reason=(
            f"Estimated short gaps (<= {max_gap_days} days, valid values on both sides) in continuous "
            "variables by linear interpolation and flagged them as estimated. Rainfall gaps are never "
            "filled; longer gaps are left unresolved."
        ),
    )
    return out, step, gaps


def _why(var: str, length: int, max_gap: int, bounded: bool) -> str:
    if var in NEVER_FILL:
        return "rainfall is never interpolated; missing rain is not zero rain"
    if not bounded:
        return "gap touches the start or end of the record"
    return f"gap of {length} days exceeds the {max_gap}-day limit"

"""Pipeline step: qa (Data Journey stage "Check"). Owner: M3.

Decodes fill values, makes absent days explicit and marks duplicates. Never touches ``raw_value``.
See DEVELOPMENT_GUIDE.md section 6: distinguish duplicates, rejected records and missing values.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ftm.contracts.models import ProcessingStep, QualityFlag, ValueKind

WORK_COLUMNS = ["processed_value", "quality_flag", "value_kind", "imputation_method", "flag_reason"]


def check(
    obs: pd.DataFrame,
    *,
    fill_value: float,
    start: date,
    end: date,
    value_kind: ValueKind,
) -> tuple[pd.DataFrame, ProcessingStep]:
    """Return observations with work columns added, plus inserted rows for absent days.

    ``obs`` needs ``date, variable, unit, raw_value`` (as produced by an adapter's parser).
    """
    df = obs.copy()
    df["processed_value"] = df["raw_value"].astype("float64")
    df["quality_flag"] = QualityFlag.OK.value
    df["value_kind"] = value_kind.value
    df["imputation_method"] = None
    df["flag_reason"] = None

    # 1. Fill values / nulls -> missing. A real 0.0 is kept as 0.0.
    is_fill = df["raw_value"].isna() | np.isclose(df["raw_value"].astype("float64"), fill_value)
    df.loc[is_fill, ["processed_value", "quality_flag", "flag_reason"]] = [
        np.nan,
        QualityFlag.MISSING.value,
        f"source fill value {fill_value}",
    ]

    # 2. Duplicates: keep the first row per (variable, date); later rows are flagged, not dropped.
    dup = df.duplicated(subset=["variable", "date"], keep="first")
    first_values = df[~dup].set_index(["variable", "date"])["raw_value"]
    conflicting = 0
    for idx in df.index[dup]:
        key = (df.at[idx, "variable"], df.at[idx, "date"])
        if not _same(df.at[idx, "raw_value"], first_values.get(key)):
            conflicting += 1
    df.loc[dup, ["processed_value", "quality_flag", "flag_reason"]] = [
        np.nan,
        QualityFlag.DUPLICATE.value,
        "duplicate (variable, date); first occurrence kept",
    ]

    # 3. Days the source never delivered become explicit missing rows (raw_value stays None).
    expected_dates = pd.date_range(start, end, freq="D").date
    units = df.drop_duplicates("variable").set_index("variable")["unit"].to_dict()
    present = set(zip(df["variable"], df["date"], strict=True))
    absent_rows = [
        {
            "date_key": d.strftime("%Y%m%d"),
            "date": d,
            "variable": var,
            "unit": unit,
            "raw_value": None,
            "processed_value": np.nan,
            "quality_flag": QualityFlag.MISSING.value,
            "value_kind": value_kind.value,
            "imputation_method": None,
            "flag_reason": "not delivered by source",
        }
        for var, unit in units.items()
        for d in expected_dates
        if (var, d) not in present
    ]
    if absent_rows:
        df = pd.concat([df, pd.DataFrame(absent_rows)], ignore_index=True)
    out_of_range = (df["date"] < start) | (df["date"] > end)
    df.loc[out_of_range & (df["quality_flag"] == QualityFlag.OK.value), ["quality_flag", "flag_reason"]] = [
        QualityFlag.FLAGGED.value,
        "outside requested date range",
    ]
    df = df.sort_values(["variable", "date"], kind="stable").reset_index(drop=True)

    per_variable = {
        var: {
            "expected": len(expected_dates),
            "received": int((obs["variable"] == var).sum()),
            "missing": int((g["quality_flag"] == QualityFlag.MISSING.value).sum()),
            "duplicate": int((g["quality_flag"] == QualityFlag.DUPLICATE.value).sum()),
            "flagged": int((g["quality_flag"] == QualityFlag.FLAGGED.value).sum()),
        }
        for var, g in df.groupby("variable")
    }
    step = ProcessingStep(
        name="qa",
        params={"fill_value": fill_value, "start": start.isoformat(), "end": end.isoformat()},
        affected_count=int(is_fill.sum() + dup.sum() + len(absent_rows) + out_of_range.sum()),
        reason=(
            "Decoded source fill values as missing, flagged duplicate records (first kept), and added "
            "explicit missing rows for days the source did not deliver."
        ),
    )
    step.params["per_variable"] = per_variable
    step.params["conflicting_duplicates"] = conflicting
    step.params["absent_rows_added"] = len(absent_rows)
    return df, step


def _same(a: object, b: object) -> bool:
    if a is None or b is None or pd.isna(a) or pd.isna(b):  # type: ignore[arg-type]
        return (a is None or pd.isna(a)) and (b is None or pd.isna(b))  # type: ignore[arg-type]
    return bool(np.isclose(float(a), float(b)))  # type: ignore[arg-type]

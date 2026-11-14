"""Growing-season detection from quality-filtered MODIS VI. Owner: M5.

Suggests growing periods and possible low-cover windows; never identifies crop species or exact planting
dates. Low VI is not proof of bare soil. Fall back to a disclosed local calendar when the signal is weak.

Method (pre-registered in docs/validation-plan.md section 2):
1. Use only composites that pass QA (SummaryQA good/marginal). Others are dropped, not repaired.
2. Put values on the regular 16-day composite grid (date = composite start + 8 days). Bridge gaps of at
   most 2 composites by linear interpolation (flagged); longer gaps split the series into segments.
3. Smooth each segment with a Savitzky-Golay filter (scipy.signal.savgol_filter).
4. Seasons: peaks with prominence >= 0.1 NDVI, at least 4 composites (64 days) apart, so two seasons per
   year are possible (e.g. winter wheat then a summer crop). Start/end = the date the smoothed curve
   crosses ``fraction`` of the season's rise/fall above its left/right minimum: the amplitude-threshold
   method of TIMESAT (Jonsson & Eklundh 2004, doi:10.1016/j.cageo.2004.05.006).
5. Fallback rule (declared heuristic): a season with < 50 % QA-passing composites, or amplitude < 0.1,
   is marked ``fallback_recommended`` and the app shows the local calendar instead.

Tuning (window, polyorder, fraction) uses only 2001-2014 and refuses the held-out 2020-2025 years unless
``unlock_test=True`` (validation plan section 1).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter

from ftm.contracts.models import JourneyStage, JourneyStageName, StageStatus

COMPOSITE_DAYS = 16
MAX_BRIDGE_COMPOSITES = 2
MIN_AMPLITUDE = 0.1
MIN_QA_SHARE = 0.5
MIN_SEPARATION_COMPOSITES = 4
TUNING_GRID: dict[str, tuple[Any, ...]] = {"window": (5, 7, 9), "polyorder": (2, 3), "fraction": (0.2, 0.3, 0.5)}
TUNING_YEARS = range(2001, 2015)
TEST_YEARS = range(2020, 2026)
CAVEATS = (
    "Suggested growing periods from satellite greenness, not observed planting or harvest dates.",
    "A season's crop type is not identified.",
    "Low vegetation between seasons is not proof of bare soil (harvest residue, cloud or crop type can explain it).",
)


class TestPeriodLockedError(PermissionError):
    """Tuning or evaluation touched the held-out test years without an explicit unlock."""

    __test__ = False  # not a pytest class


@dataclass(frozen=True)
class PhenologyParams:
    window: int = 7  # composites; middle of the pre-declared grid until tuning picks one
    polyorder: int = 2
    fraction: float = 0.3

    def __post_init__(self) -> None:
        if self.window % 2 == 0 or self.window <= self.polyorder:
            raise ValueError("window must be odd and larger than polyorder")
        if not 0 < self.fraction < 1:
            raise ValueError("fraction must be between 0 and 1")


@dataclass
class Season:
    start: date | None  # None = rise happens before the data/segment starts
    peak: date
    end: date | None  # None = fall happens after the data/segment ends
    peak_ndvi: float
    amplitude: float  # min of rise and fall amplitude (NDVI units)
    qa_share: float  # share of composites in the season that passed QA (rest were bridged)
    fallback_recommended: bool
    notes: list[str] = field(default_factory=list)

    @property
    def length_days(self) -> int | None:
        return None if self.start is None or self.end is None else (self.end - self.start).days


@dataclass
class PhenologyResult:
    series: pd.DataFrame  # date, ndvi_qa, ndvi_filled, ndvi_smooth, bridged, segment
    seasons: list[Season]
    low_cover_windows: list[tuple[date, date]]
    params: PhenologyParams
    source_ids: list[str] = field(default_factory=list)
    processing_run_id: str | None = None

    def seasons_frame(self) -> pd.DataFrame:
        rows = [{**asdict(s), "length_days": s.length_days} for s in self.seasons]
        return pd.DataFrame(rows)


# --------------------------------------------------------------------------- detection


def prepare(composites: pd.DataFrame, value: str = "ndvi") -> pd.DataFrame:
    """QA filter, regular grid, short-gap bridging and segment ids (validation plan section 2, steps 1-2)."""
    c = composites.sort_values("composite_start").reset_index(drop=True)
    out = pd.DataFrame({"date": [d + timedelta(days=8) for d in c["composite_start"]]})
    out["ndvi_qa"] = np.where(c["qa_pass"].astype(bool), c[value].astype(float), np.nan)
    is_gap = out["ndvi_qa"].isna()
    run_id = (is_gap != is_gap.shift()).cumsum()
    run_len = is_gap.groupby(run_id).transform("sum")
    bridgeable = is_gap & (run_len <= MAX_BRIDGE_COMPOSITES)
    filled = out["ndvi_qa"].interpolate(limit_area="inside")
    out["ndvi_filled"] = np.where(is_gap & ~bridgeable, np.nan, filled)
    out["bridged"] = bridgeable & out["ndvi_filled"].notna()
    breaks = out["ndvi_filled"].isna()
    out["segment"] = np.where(breaks, -1, (breaks != breaks.shift()).cumsum())
    return out


def detect_seasons(
    composites: pd.DataFrame,
    params: PhenologyParams | None = None,
    *,
    value: str = "ndvi",
) -> PhenologyResult:
    """Detect growing seasons in a composite series (as returned by ``ftm.data.vegetation.get_vi_composites``)."""
    p = params or PhenologyParams()
    s = prepare(composites, value)
    s["ndvi_smooth"] = np.nan
    seasons: list[Season] = []
    for _seg_id, seg in s[s.segment >= 0].groupby("segment"):
        if len(seg) < p.window:
            continue  # too short to smooth: no season claimed
        sm = savgol_filter(seg["ndvi_filled"].to_numpy(), p.window, p.polyorder, mode="interp")
        s.loc[seg.index, "ndvi_smooth"] = sm
        seasons += _seasons_in_segment(seg.assign(ndvi_smooth=sm).reset_index(drop=True), p)
    lows = [(a.end, b.start) for a, b in itertools.pairwise(seasons) if a.end and b.start and b.start > a.end]
    return PhenologyResult(
        series=s,
        seasons=seasons,
        low_cover_windows=lows,
        params=p,
        source_ids=list(composites.attrs.get("source_ids", [])),
        processing_run_id=composites.attrs.get("processing_run_id"),
    )


def _seasons_in_segment(seg: pd.DataFrame, p: PhenologyParams) -> list[Season]:
    y = seg["ndvi_smooth"].to_numpy()
    dates = list(seg["date"])
    peaks, _ = find_peaks(y, prominence=MIN_AMPLITUDE, distance=MIN_SEPARATION_COMPOSITES)
    out = []
    for k, pk in enumerate(peaks):
        lo = peaks[k - 1] if k > 0 else 0
        hi = peaks[k + 1] if k + 1 < len(peaks) else len(y) - 1
        left = lo + int(np.argmin(y[lo : pk + 1]))
        right = pk + int(np.argmin(y[pk : hi + 1]))
        rise, fall = y[pk] - y[left], y[pk] - y[right]
        start = _crossing(y, dates, left, pk, y[left] + p.fraction * rise, rising=True)
        end = _crossing(y, dates, pk, right, y[right] + p.fraction * fall, rising=False)
        notes = []
        if start is None:
            notes.append("rise starts before the data or a long gap; start not claimed")
        if end is None:
            notes.append("fall ends after the data or a long gap; end not claimed")
        span = seg.iloc[left : right + 1]
        qa_share = float((~span["bridged"]).mean())
        if span["bridged"].any():
            notes.append(f"{int(span['bridged'].sum())} bridged composite(s) inside the season")
        amplitude = float(min(rise, fall))
        fallback = qa_share < MIN_QA_SHARE or amplitude < MIN_AMPLITUDE
        if fallback:
            notes.append("weak or cloudy signal: show the local calendar instead (validation plan section 2)")
        out.append(
            Season(
                start, dates[pk], end, round(float(y[pk]), 3), round(amplitude, 3), round(qa_share, 2), fallback, notes
            )
        )
    return out


def _crossing(y: np.ndarray, dates: Sequence[date], a: int, b: int, thr: float, *, rising: bool) -> date | None:
    """Date where the smoothed curve crosses ``thr`` between indices a..b, linearly interpolated."""
    rng = range(a, b) if rising else range(b - 1, a - 1, -1)
    for i in rng:
        lo, hi = (i, i + 1)
        if (y[lo] < thr <= y[hi]) if rising else (y[hi] < thr <= y[lo]):
            frac = (thr - y[lo]) / (y[hi] - y[lo])
            return dates[lo] + timedelta(days=round(frac * (dates[hi] - dates[lo]).days))
    return None


# --------------------------------------------------------------------------- evaluation & tuning


def evaluate_starts(
    seasons: Iterable[Season], reference: Iterable[date], *, max_days: int = 60, unlock_test: bool = False
) -> dict[str, Any]:
    """Compare detected season starts with reference start dates (e.g. farmer records or NASS 50 % planted).

    Each reference date is matched to the nearest detected start within ``max_days``. Reports bias and median
    absolute error in days, detection rate, extra detected seasons and n.
    """
    refs = sorted(reference)
    _guard_years((r.year for r in refs), unlock_test)
    starts = [s.start for s in seasons if s.start is not None and s.start.year in {r.year for r in refs}]
    errors, used = [], set()
    for r in refs:
        best = min(((abs((s - r).days), i, s) for i, s in enumerate(starts) if i not in used), default=None)
        if best and best[0] <= max_days:
            used.add(best[1])
            errors.append((best[2] - r).days)
    n = len(refs)
    return {
        "n_reference": n,
        "n_matched": len(errors),
        "detection_rate": round(len(errors) / n, 3) if n else None,
        "bias_days": round(float(np.mean(errors)), 1) if errors else None,
        "median_abs_error_days": round(float(np.median(np.abs(errors))), 1) if errors else None,
        "extra_detected": len(starts) - len(used),
        "errors_days": errors,
    }


def tune(
    composites: pd.DataFrame,
    reference: Iterable[date],
    *,
    grid: dict[str, tuple[Any, ...]] = TUNING_GRID,
    years: Iterable[int] = TUNING_YEARS,
    unlock_test: bool = False,
) -> tuple[PhenologyParams, pd.DataFrame]:
    """Pick the grid point with the lowest median absolute start error on ``years`` (validation plan §2.4)."""
    years = set(years)
    _guard_years(years, unlock_test)
    refs = [r for r in reference if r.year in years]
    comps = composites[[d.year in years for d in composites["composite_start"]]]
    rows = []
    for w, po, f in itertools.product(grid["window"], grid["polyorder"], grid["fraction"]):
        try:
            prm = PhenologyParams(w, po, f)
        except ValueError:
            continue
        ev = evaluate_starts(detect_seasons(comps, prm).seasons, refs, unlock_test=unlock_test)
        rows.append(
            {"window": w, "polyorder": po, "fraction": f, **{k: v for k, v in ev.items() if k != "errors_days"}}
        )
    table = pd.DataFrame(rows).sort_values(["median_abs_error_days", "detection_rate"], ascending=[True, False])
    best = table.iloc[0]
    return PhenologyParams(int(best.window), int(best.polyorder), float(best.fraction)), table


def _guard_years(years: Iterable[int], unlock_test: bool) -> None:
    touched = sorted({y for y in years if y in TEST_YEARS})
    if touched and not unlock_test:
        raise TestPeriodLockedError(f"held-out test years {touched} are locked (validation plan section 1)")


# --------------------------------------------------------------------------- Data Journey payload


def extract_stage(result: PhenologyResult, *, is_demo: bool = False) -> JourneyStage:
    """Payload for the Data Journey 'Extract' card: one curve, season markers, plain-language caveats."""
    n = len(result.seasons)
    weak = sum(s.fallback_recommended for s in result.seasons)
    s = result.series
    status = StageStatus.WARNING if weak else (StageStatus.OK if n else StageStatus.UNAVAILABLE)
    return JourneyStage(
        stage=JourneyStageName.EXTRACT,
        status=status,
        summary=(
            f"{n} suggested growing periods detected from satellite greenness"
            + (f"; {weak} too weak or cloudy, so the local calendar is shown for those." if weak else ".")
        ),
        source_ids=result.source_ids,
        processing_run_id=result.processing_run_id,
        chart={
            "type": "vi_curve",
            "dates": [d.isoformat() for d in s["date"]],
            "ndvi_qa": [None if pd.isna(v) else round(float(v), 3) for v in s["ndvi_qa"]],
            "ndvi_smooth": [None if pd.isna(v) else round(float(v), 3) for v in s["ndvi_smooth"]],
            "seasons": [
                {
                    "start": x.start.isoformat() if x.start else None,
                    "peak": x.peak.isoformat(),
                    "end": x.end.isoformat() if x.end else None,
                    "fallback": x.fallback_recommended,
                }
                for x in result.seasons
            ],
            "low_cover": [[a.isoformat(), b.isoformat()] for a, b in result.low_cover_windows],
        },
        details={
            "method": "QA-filtered NDVI, Savitzky-Golay smoothing, amplitude-threshold start/end (TIMESAT)",
            "params": asdict(result.params),
            "max_bridged_composites": MAX_BRIDGE_COMPOSITES,
            "fallback_rule": f"QA share < {MIN_QA_SHARE} or amplitude < {MIN_AMPLITUDE}",
            "caveats": list(CAVEATS),
        },
        is_demo=is_demo,
    )

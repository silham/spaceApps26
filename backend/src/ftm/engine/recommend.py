"""Suggested rotations under the seasonal prediction (D16). Owner: M4.

Method (guide §4: constraints filter, priorities order, no hidden score):

1. **Crops and dates.** A catalog crop is eligible when it has complete stage lengths, a cited base temperature
   (FAO AquaCrop default ``Tbase``) and, while a yield floor is set, a seasonal Ky. A planting date (the 1st or
   15th of a month) is eligible when it falls within a month of the planting month of the FAO-56 Table 11 row its
   stage lengths come from, and the mean temperature of each 30-day window of the first 60 days (establishment)
   reaches ``Tbase`` on at least 80% of the weather paths: below ``Tbase`` the crop does not develop (AquaCrop's
   growing-degree definition). Later cold is not tested: winter crops are dormant then, and frost damage and
   dormancy are not modelled.
2. **Sequences.** One to three seasons; each next season starts on the earliest eligible date at least
   ``GAP_DAYS`` after the previous harvest. Three-season sequences extend only the best two-season ones.
3. **Water.** Each candidate is first simulated rainfed; a season whose median relative yield misses the farmer's
   floor is irrigated (when allowed) and the candidate simulated again. Irrigation is therefore used only where
   the floor needs it.
4. **Choice.** Stage 1 runs every candidate on a few shared weighted paths; the non-dominated set on (possible
   low-cover days, irrigation, soil-health rules met) is ordered by the farmer's priorities with stated
   tolerances, keeping one option per crop sequence, and the best few run again on the full path set with
   per-path differences to current practice.

Thresholds below are engine choices, not calibrated values; they are recorded with every suggestion (D16).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ftm.contracts.models import SeasonPlan, SimulationMode, Strategy
from ftm.engine.ensemble import (
    BlockPool,
    SoilRunConfig,
    bootstrap_paths,
    build_path_forcing,
    daily_weather,
    horizon_blocks,
    path_metrics,
    run_strategies_on_path,
)
from ftm.engine.forcing import TMAX, TMIN, usable_values
from ftm.engine.params import CropEntry
from ftm.engine.rotation import SUPPORTED_IRRIGATION_RULE, missing_parameters, stage_lengths
from ftm.engine.soil_health import rules_met, soil_rules
from ftm.engine.yield_response import REL_YIELD_PREFIX, yield_metrics

WINDOW_DAYS = 30
ESTABLISH_DAYS = 60
TEMPERATURE_SHARE = 0.8
GAP_DAYS = 14
FIRST_START_DAYS = 365  # the first season starts within the first year of the horizon
STARTS_PER_RUN = 2  # per crop and eligible run of dates: its first date and one a month later
TOP_TWO_SEASON = 20  # two-season sequences extended with a third season
STAGE1_PATHS = 12
STAGE2_PATHS = 100
SHOW = 5
TOLERANCE = {"cover": 7.0, "irrigation": 10.0, "soil_health": 0.0}  # differences below these count as ties
METRIC = {"cover": "possible_low_cover_days", "irrigation": "irrigation_mm"}

ASSUMPTIONS = (
    f"A planting date is used only if each {WINDOW_DAYS}-day mean temperature of the first {ESTABLISH_DAYS} days "
    f"reaches the crop's base temperature on at least {TEMPERATURE_SHARE:.0%} of weather paths; later cold, frost "
    "damage and winter dormancy are not modelled.",
    f"Planting dates are the 1st and 15th of each month; a next crop is planted at least {GAP_DAYS} days after "
    "harvest.",
    "Each season is rainfed unless its median relative yield misses your floor; then it is irrigated (if allowed).",
    f"Ties: differences under {TOLERANCE['cover']:g} possible low-cover days or {TOLERANCE['irrigation']:g} mm of "
    "irrigation count as equal when ordering by your priorities.",
    "Crop stage lengths are generic FAO-56 Table 11 rows, so planting stays within a month of that row's planting "
    "month (six months later south of the equator); not checked against a local planting calendar.",
)


@dataclass(frozen=True)
class Constraints:
    priorities: tuple[str, str, str]
    irrigation_allowed: bool
    max_irrigation_mm: float | None
    exclude: frozenset[str]
    require: str | None
    max_seasons: int
    min_relative_yield_pct: float
    available: frozenset[str] | None = None
    southern_hemisphere: bool = False


@dataclass
class Evaluated:
    strategy: Strategy
    per_path: list[dict[str, float]]  # metrics per path
    soil: list  # list[SoilRuleResult]
    objectives: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Paths:
    frames: list[pd.DataFrame]  # path forcing, strategy calendar
    tmean: np.ndarray  # paths x days, degC (NaN where unusable)
    start: date


def build_paths(
    forcing: pd.DataFrame,
    et0: pd.DataFrame,
    pool: BlockPool,
    horizon: tuple[date, date],
    *,
    n_paths: int,
    seed: int,
    first_block_weights: Mapping[int, float] | None,
) -> Paths:
    years = bootstrap_paths(
        pool, n_paths=n_paths, horizon_years=horizon_blocks(horizon), seed=seed, first_block_weights=first_block_weights
    )
    weather = daily_weather(forcing, et0)
    tx = pd.Series(usable_values(forcing, TMAX), index=forcing.index)
    tn = pd.Series(usable_values(forcing, TMIN), index=forcing.index)
    anchor = horizon[0].strftime("%m-%d")
    frames, temps = [], []
    for y in years:
        pf = build_path_forcing(weather, y, anchor_md=anchor, base_year=horizon[0].year)
        src = pd.DatetimeIndex(pf["source_date"])
        frames.append(pf)
        temps.append(((tx.reindex(src) + tn.reindex(src)) / 2).to_numpy(dtype="float64"))
    n = min(len(t) for t in temps)
    return Paths(frames, np.vstack([t[:n] for t in temps]), horizon[0])


def eligible_crops(crops: Mapping[str, CropEntry], c: Constraints) -> dict[str, CropEntry]:
    out = {}
    for cid, e in crops.items():
        p = e.profile
        if cid in c.exclude or (c.available is not None and cid not in c.available):
            continue
        if missing_parameters(e) or p.t_base_c is None or p.t_base_c.value is None or not p.table11_planting_months:
            continue
        if c.min_relative_yield_pct > 0 and (p.ky_season is None or p.ky_season.value is None):
            continue
        out[cid] = e
    return out


class _Temperature:
    """Cached test: can this crop be planted on this horizon day (index)?"""

    def __init__(self, paths: Paths, crops: Mapping[str, CropEntry]) -> None:
        self.t = paths.tmean
        self.crops = crops
        self.cache: dict[tuple[str, int], bool] = {}
        # cumulative sums for fast window means (NaN days make a window unusable)
        valid = np.isfinite(self.t)
        self.cs = np.concatenate([np.zeros((self.t.shape[0], 1)), np.cumsum(np.where(valid, self.t, 0.0), axis=1)], 1)
        self.cv = np.concatenate([np.zeros((self.t.shape[0], 1)), np.cumsum(valid, axis=1)], 1)

    def ok(self, cid: str, day: int) -> bool:
        key = (cid, day)
        if key in self.cache:
            return self.cache[key]
        e = self.crops[cid]
        ini, dev, mid, late = stage_lengths(e)
        tbase = float(e.profile.t_base_c.value)  # type: ignore[union-attr,arg-type]
        grow_end = day + ESTABLISH_DAYS
        result = day + ini + dev + mid + late <= self.t.shape[1]
        w = day
        while result and w < grow_end:
            hi = min(w + WINDOW_DAYS, self.t.shape[1])
            n = self.cv[:, hi] - self.cv[:, w]
            mean = np.where(n > 0, (self.cs[:, hi] - self.cs[:, w]) / np.maximum(n, 1), -np.inf)
            result = float(np.mean(mean >= tbase)) >= TEMPERATURE_SHARE
            w += WINDOW_DAYS
        self.cache[key] = result
        return result


def _start_days(start: date, n_days: int) -> list[int]:
    return [k for k in range(n_days) if (start + timedelta(days=k)).day in (1, 15)]


def in_table11_months(entry: CropEntry, d: date, southern: bool) -> bool:
    """Within a month of the planting month(s) of the FAO-56 Table 11 row the stage lengths come from (shifted six
    months south of the equator): those lengths describe that season, not any planting date."""
    months = entry.profile.table11_planting_months or []
    m = (d.month - 1 + (6 if southern else 0)) % 12 + 1
    return any(min((m - x) % 12, (x - m) % 12) <= 1 for x in months)


def _season(entry: CropEntry, plant: date, irrigated: bool) -> SeasonPlan:
    end = plant + timedelta(days=sum(stage_lengths(entry)) - 1)
    rule = SUPPORTED_IRRIGATION_RULE if irrigated else None
    return SeasonPlan(crop_id=entry.profile.id, plant_date=plant, end_date=end, irrigation_rule=rule)


def _name(seasons: Sequence[SeasonPlan], crops: Mapping[str, CropEntry]) -> str:
    parts = [
        f"{crops[s.crop_id].profile.name}{' (irrigated)' if s.irrigation_rule else ''}" for s in seasons if s.crop_id
    ]
    return " → ".join(parts)


def generate(
    paths: Paths,
    crops: Mapping[str, CropEntry],
    c: Constraints,
    *,
    earliest: date,
    extend_from: list[list[SeasonPlan]] | None = None,
) -> list[list[SeasonPlan]]:
    """Rainfed season sequences. Without ``extend_from``: one- and two-season sequences; with it: those
    sequences extended by one more season."""
    temp = _Temperature(paths, crops)
    n_days = paths.tmean.shape[1]
    starts = _start_days(paths.start, n_days)
    day_of = {(paths.start + timedelta(days=k)): k for k in starts}

    def next_start(cid: str, after: date) -> date | None:
        for k in starts:
            d = paths.start + timedelta(days=k)
            if d >= after and in_table11_months(crops[cid], d, c.southern_hemisphere) and temp.ok(cid, k):
                return d
        return None

    def follow(seq: list[SeasonPlan]) -> list[list[SeasonPlan]]:
        after = seq[-1].end_date + timedelta(days=GAP_DAYS)
        out = []
        for cid, e in crops.items():
            d = next_start(cid, after)
            if d is not None:
                out.append([*seq, _season(e, d, False)])
        return out

    if extend_from is not None:
        return [s for seq in extend_from for s in follow(seq)]
    first: list[list[SeasonPlan]] = []
    for cid, e in crops.items():
        runs, prev = [], False
        for k in starts:
            d = paths.start + timedelta(days=k)
            if (d - paths.start).days >= FIRST_START_DAYS:
                break
            ok = d >= earliest and in_table11_months(e, d, c.southern_hemisphere) and temp.ok(cid, k)
            if ok and not prev:
                runs.append([d])
            elif ok and runs and len(runs[-1]) < STARTS_PER_RUN and (d - runs[-1][0]).days >= 28:
                runs[-1].append(d)
            prev = ok
        first += [[_season(e, d, False)] for run in runs for d in run]
    del day_of
    out = list(first)
    if c.max_seasons >= 2:
        for seq in first:
            out += follow(seq)
    return out


def _evaluate(
    strategies: list[Strategy],
    paths: Sequence[pd.DataFrame],
    crops: Mapping[str, CropEntry],
    config: SoilRunConfig,
    standing: SeasonPlan | None,
    progress: Callable[[float], None] | None = None,
) -> dict[str, list[dict[str, float]]]:
    per: dict[str, list[dict[str, float]]] = {s.id: [] for s in strategies}
    by_id = {s.id: s for s in strategies}
    for i, pf in enumerate(paths):
        traces, _ = run_strategies_on_path(
            pf,
            strategies,
            crops,
            config,
            mode=SimulationMode.IRRIGATION_NEEDED,
            allocation_mm_per_season=None,
            standing=standing,
        )
        for sid, t in traces.items():
            per[sid].append({**path_metrics(t), **yield_metrics(t, by_id[sid], crops)})
        if progress:
            progress((i + 1) / len(paths))
    return per


def _median(per_path: list[dict[str, float]], metric: str) -> float:
    vals = [p[metric] for p in per_path if metric in p]
    return float(np.median(vals)) if vals else float("nan")


def _short_seasons(per_path: list[dict[str, float]], n: int, floor: float) -> list[int]:
    if floor <= 0:  # no floor: a crop without Ky (no yield metric) is not "short"
        return []
    return [k for k in range(n) if not (_median(per_path, f"{REL_YIELD_PREFIX}{k}") >= floor)]


def _dominates(a: dict[str, float], b: dict[str, float]) -> bool:
    better = (a["cover"] <= b["cover"], a["irrigation"] <= b["irrigation"], a["soil_health"] >= b["soil_health"])
    strictly = (a["cover"] < b["cover"], a["irrigation"] < b["irrigation"], a["soil_health"] > b["soil_health"])
    return all(better) and any(strictly)


def order_key(obj: dict[str, float], priorities: Sequence[str]) -> tuple[float, ...]:
    key = []
    for p in priorities:
        v = obj[p]
        tol = TOLERANCE[p]
        binned = round(v / tol) if tol > 0 else v
        key.append(-binned if p == "soil_health" else binned)
    return (*key, -obj.get("yield", 0.0))


@dataclass
class Suggestion:
    ranked: list[Evaluated]  # best first, stage-2 metrics
    current: Evaluated | None
    considered: int
    stage2_paths: int


def suggest(
    forcing: pd.DataFrame,
    et0: pd.DataFrame,
    pool: BlockPool,
    crops: Mapping[str, CropEntry],
    config: SoilRunConfig,
    c: Constraints,
    *,
    site_id: str,
    horizon: tuple[date, date],
    first_block_weights: Mapping[int, float] | None,
    seed: int,
    standing: SeasonPlan | None = None,
    current: Strategy | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> Suggestion:
    say = progress or (lambda f, m: None)
    usable = eligible_crops(crops, c)
    if not usable:
        raise ValueError("no catalog crop has the cited parameters these suggestions need (base temperature, Ky)")
    say(0.02, "Preparing weather paths")
    p1 = build_paths(
        forcing, et0, pool, horizon, n_paths=STAGE1_PATHS, seed=seed, first_block_weights=first_block_weights
    )
    earliest = max(horizon[0], (standing.end_date + timedelta(days=GAP_DAYS)) if standing else horizon[0])
    soil_before = standing
    n = [0]

    def make(seq: list[SeasonPlan]) -> Strategy:
        n[0] += 1
        return Strategy(id=f"cand{n[0]}", site_id=site_id, name=_name(seq, crops), seasons=seq)

    def stage1(seqs: list[list[SeasonPlan]], lo: float, hi: float) -> list[Evaluated]:
        strategies = [make(s) for s in seqs if s[-1].end_date <= horizon[1]]
        if not strategies:
            return []
        per = _evaluate(
            strategies,
            p1.frames,
            crops,
            config,
            standing,
            lambda f: say(lo + (hi - lo) * f * 0.6, "Simulating candidates"),
        )
        out, retry = [], []
        for s in strategies:
            short = _short_seasons(per[s.id], len(s.seasons), c.min_relative_yield_pct)
            if not short:
                out.append(Evaluated(s, per[s.id], []))
            elif c.irrigation_allowed:
                seasons = [
                    _season(crops[x.crop_id], x.plant_date, k in short) if x.crop_id else x  # type: ignore[index]
                    for k, x in enumerate(s.seasons)
                ]
                retry.append(Strategy(id=s.id, site_id=site_id, name=_name(seasons, crops), seasons=seasons))
        if retry:
            per2 = _evaluate(
                retry,
                p1.frames,
                crops,
                config,
                standing,
                lambda f: say(lo + (hi - lo) * (0.6 + 0.4 * f), "Adding irrigation where needed"),
            )
            out += [
                Evaluated(s, per2[s.id], [])
                for s in retry
                if not _short_seasons(per2[s.id], len(s.seasons), c.min_relative_yield_pct)
            ]
        for e in out:
            e.soil = soil_rules(e.strategy, crops, before=soil_before)
            e.objectives = _objectives(e)
        return [e for e in out if c.max_irrigation_mm is None or e.objectives["irrigation"] <= c.max_irrigation_mm]

    say(0.05, "Finding crops and planting dates that suit the predicted temperatures")
    seqs = generate(p1, usable, c, earliest=earliest)
    evaluated = stage1(seqs, 0.05, 0.55)
    if c.max_seasons >= 3:
        twos = sorted(
            (e for e in evaluated if len(e.strategy.seasons) == 2), key=lambda e: order_key(e.objectives, c.priorities)
        )[:TOP_TWO_SEASON]
        threes = generate(p1, usable, c, earliest=earliest, extend_from=[e.strategy.seasons for e in twos])
        evaluated += stage1(threes, 0.55, 0.8)
    considered = n[0]
    if c.require:
        evaluated = [e for e in evaluated if any(s.crop_id == c.require for s in e.strategy.seasons)]
    front = [e for e in evaluated if not any(_dominates(o.objectives, e.objectives) for o in evaluated)]
    front.sort(key=lambda e: order_key(e.objectives, c.priorities))
    # One option per crop sequence (the best-placed dates and irrigation), so the options shown differ in crops.
    seen: set[tuple[str | None, ...]] = set()
    best = []
    for e in front:
        crops_seq = tuple(s.crop_id for s in e.strategy.seasons)
        if crops_seq not in seen:
            seen.add(crops_seq)
            best.append(e)
        if len(best) == SHOW:
            break

    say(0.82, "Checking the best options on all weather paths")
    p2 = build_paths(
        forcing, et0, pool, horizon, n_paths=STAGE2_PATHS, seed=seed, first_block_weights=first_block_weights
    )
    final = [e.strategy for e in best] + ([current] if current else [])
    per = (
        _evaluate(
            final,
            p2.frames,
            crops,
            config,
            standing,
            lambda f: say(0.82 + 0.17 * f, "Checking the best options on all weather paths"),
        )
        if final
        else {}
    )
    ranked = []
    for e in best:
        r = Evaluated(e.strategy, per[e.strategy.id], e.soil)
        r.objectives = _objectives(r)
        ranked.append(r)
    ranked.sort(key=lambda e: order_key(e.objectives, c.priorities))  # final order from the full path set
    cur = None
    if current is not None:
        cur = Evaluated(current, per[current.id], soil_rules(current, crops, before=soil_before))
        cur.objectives = _objectives(cur)
    say(1.0, "Done")
    return Suggestion(ranked, cur, considered, STAGE2_PATHS)


def _objectives(e: Evaluated) -> dict[str, float]:
    ys = [_median(e.per_path, k) for k in e.per_path[0] if k.startswith(REL_YIELD_PREFIX)] if e.per_path else []
    return {
        "cover": _median(e.per_path, METRIC["cover"]),
        "irrigation": _median(e.per_path, METRIC["irrigation"]),
        "soil_health": float(rules_met(e.soil)),
        "yield": float(np.mean(ys)) if ys else 0.0,
    }

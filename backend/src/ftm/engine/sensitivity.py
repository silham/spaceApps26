"""Sensitivity of the strategy ranking to uncertain inputs (validation plan section 4). Owner: M4.

Inputs varied (low / mid / high), always on the *same* paired weather paths: the seed, sample pool,
horizon and path count are held fixed, so every case draws the same historical years.

| Input | Levels | Source of the range |
|---|---|---|
| AWC | provider low / mid / high | soil source (SSURGO awc_l / awc_r / awc_h) or a labelled assumption |
| Initial soil water | 25 / 50 / 75 % of field capacity | declared assumption |
| Planting date | -14 / 0 / +14 days | declared shift; the whole crop season moves, harvest included |
| Irrigation allocation | -20 / 0 / +20 % | declared assumption (fixed-allocation mode only) |

A shifted season that breaks a hard constraint (overlap, horizon, planting window) becomes infeasible
with its reason; it is never moved back silently. Rankings order strategies by the median (p50) of a
metric; equal medians are a tie. This tests robustness, not accuracy.
"""

from __future__ import annotations

import dataclasses
import itertools
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Literal

from ftm.contracts.models import SimulationMode, Strategy
from ftm.engine.params import with_awc
from ftm.engine.runner import EngineOutput, EngineRequest, run_engine

Level = Literal["low", "mid", "high"]
RANKING_METRICS = ("irrigation_mm", "water_stress_days", "cover_days", "possible_low_cover_days")
INITIAL_FRACTIONS: dict[Level, float] = {"low": 0.25, "mid": 0.5, "high": 0.75}
PLANTING_SHIFT_DAYS: dict[Level, int] = {"low": -14, "mid": 0, "high": 14}
ALLOCATION_FACTORS: dict[Level, float] = {"low": 0.8, "mid": 1.0, "high": 1.2}
INPUTS = ("awc", "initial_water", "planting_date", "allocation")


@dataclass(frozen=True)
class AwcBounds:
    low: float
    mid: float
    high: float
    source: str  # e.g. "SSURGO awc_l / awc_r / awc_h, 0-1 m"

    def value(self, level: Level) -> float:
        return {"low": self.low, "mid": self.mid, "high": self.high}[level]


@dataclass(frozen=True)
class SensitivityCase:
    awc: Level = "mid"
    initial_water: Level = "mid"
    planting_date: Level = "mid"
    allocation: Level = "mid"

    @property
    def changed(self) -> dict[str, Level]:
        return {k: v for k, v in dataclasses.asdict(self).items() if v != "mid"}

    @property
    def name(self) -> str:
        return ", ".join(f"{k} {v}" for k, v in self.changed.items()) or "baseline"


def shift_planting(strategy: Strategy, days: int) -> Strategy:
    """Move every crop season (planting and harvest) by ``days``; fallow seasons stay where they are."""
    if days == 0:
        return strategy
    delta = timedelta(days=days)
    seasons = [
        s
        if s.crop_id is None
        else s.model_copy(update={"plant_date": s.plant_date + delta, "end_date": s.end_date + delta})
        for s in strategy.seasons
    ]
    return strategy.model_copy(update={"seasons": seasons, "feasibility": None})


def apply_case(base: EngineRequest, case: SensitivityCase, awc: AwcBounds) -> EngineRequest:
    """The base request with one case's inputs; weather, seed, pool and path count are unchanged."""
    allocation = base.allocation_mm_per_season
    factor = ALLOCATION_FACTORS[case.allocation]
    if base.mode is SimulationMode.FIXED_ALLOCATION and allocation is not None:
        allocation = allocation * factor
    elif factor != 1.0:
        raise ValueError("allocation sensitivity applies only in fixed_allocation mode")
    soil = base.soil
    if case.awc != "mid" or awc.mid != soil.profile.available_water_capacity_mm_per_m.value:
        soil = with_awc(soil, awc.value(case.awc), f"{case.awc} bound, {awc.source}")
    shift = PLANTING_SHIFT_DAYS[case.planting_date]
    return dataclasses.replace(
        base,
        soil=soil,
        initial_fraction=INITIAL_FRACTIONS[case.initial_water],
        allocation_mm_per_season=allocation,
        strategies=[shift_planting(s, shift) for s in base.strategies],
        trace_dir=None,
    )


def one_at_a_time(*, include_allocation: bool) -> list[SensitivityCase]:
    """Baseline plus each input at its low and high level (8 + 1 cases, 6 + 1 without allocation)."""
    names = [n for n in INPUTS if include_allocation or n != "allocation"]
    cases = [SensitivityCase()]
    for name, level in itertools.product(names, ("low", "high")):
        cases.append(SensitivityCase(**{name: level}))  # type: ignore[arg-type]
    return cases


def full_grid(*, include_allocation: bool) -> list[SensitivityCase]:
    """Every combination: 3^4 = 81 cases (27 without allocation). Baseline first."""
    levels: tuple[Level, ...] = ("mid", "low", "high")
    alloc = levels if include_allocation else ("mid",)
    return [SensitivityCase(a, i, p, q) for a, i, p, q in itertools.product(levels, levels, levels, alloc)]


Ranking = tuple[tuple[str, ...], ...]  # strategy-id groups in ascending median order; a group is a tie


def ranking(out: EngineOutput, metric: str) -> Ranking | None:
    """Order feasible strategies by p50 of ``metric``; None when the metric is not available."""
    rows = [r for r in out.results if r.metric == metric and r.p50 is not None]
    if not rows:
        return None
    groups: list[list[str]] = []
    last: float | None = None
    for r in sorted(rows, key=lambda r: (r.p50, r.strategy_id)):
        assert r.p50 is not None
        if last is not None and abs(r.p50 - last) <= 1e-9:
            groups[-1].append(r.strategy_id)
        else:
            groups.append([r.strategy_id])
        last = r.p50
    return tuple(tuple(g) for g in groups)


@dataclass
class CaseResult:
    case: SensitivityCase
    run_id: str
    path_years: list[tuple[int, ...]]
    rankings: dict[str, Ranking | None]
    infeasible: dict[str, list[str]]


@dataclass
class SensitivityReport:
    cases: list[CaseResult]
    summary: dict[str, str] = field(default_factory=dict)  # metric -> plain sentence
    flips: dict[str, list[str]] = field(default_factory=dict)  # metric -> case names that change the order


def run_sensitivity(
    base: EngineRequest, cases: list[SensitivityCase], awc: AwcBounds, metrics: tuple[str, ...] = RANKING_METRICS
) -> SensitivityReport:
    """Run every case on the same weather paths and compare each ranking with the baseline's."""
    if not cases or cases[0].changed:
        raise ValueError("the first case must be the baseline (all inputs at mid)")
    results: list[CaseResult] = []
    for case in cases:
        out = run_engine(apply_case(base, case, awc))
        results.append(
            CaseResult(
                case=case,
                run_id=out.run.id,
                path_years=[o.years for o in out.outcomes],
                rankings={m: ranking(out, m) for m in metrics},
                infeasible={sid: f.reasons for sid, f in out.feasibility.items() if not f.feasible},
            )
        )
    if any(r.path_years != results[0].path_years for r in results):
        raise RuntimeError("sensitivity cases drew different weather paths; pairing is broken")

    report = SensitivityReport(results)
    ref = results[0]
    for m in metrics:
        comparable = [
            r for r in results[1:] if r.rankings[m] is not None and r.infeasible.keys() == ref.infeasible.keys()
        ]
        flips = [r.case.name for r in comparable if r.rankings[m] != ref.rankings[m]]
        not_comparable = len(results) - 1 - len(comparable)
        report.flips[m] = flips
        text = f"{m}: ranking unchanged in {len(comparable) - len(flips)} of {len(comparable)} combinations"
        text += f"; changed by: {', '.join(flips)}." if flips else "."
        if not_comparable:
            text += f" {not_comparable} combination(s) not comparable (a strategy became infeasible)."
        report.summary[m] = text
    return report

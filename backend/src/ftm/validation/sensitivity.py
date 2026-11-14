"""Sensitivity of strategy ranking to uncertain soil/management inputs. Owner: M5.

Pre-registered in docs/validation-plan.md section 4: vary AWC, initial soil water, planting-date shift and
irrigation allocation (low / mid / high), with the same paired weather paths for every combination, and
report whether the order of the three strategies changes. The engine (M4) is passed in as
``run_fn(inputs) -> {strategy_id: {metric: median value}}``.

Output: "ranking unchanged in X of Y combinations; the input that flips it is ...". The message is the
trade-off, not a single winner.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

RunFn = Callable[[dict[str, Any]], Mapping[str, Mapping[str, float]]]


@dataclass(frozen=True)
class Factor:
    name: str
    low: Any
    mid: Any
    high: Any
    basis: str  # where the range comes from (provider bounds or a declared assumption)


# Declared in the validation plan; AWC bounds come from the soil source at run time.
def default_factors(
    awc_low: float | None, awc_mid: float, awc_high: float | None, allocation_mm: float | None
) -> list[Factor]:
    if awc_low is None or awc_high is None:
        awc = Factor(
            "awc_mm_per_m", awc_mid * 0.8, awc_mid, awc_mid * 1.2, "declared assumption: +/-20 % (no provider bounds)"
        )
    else:
        awc = Factor("awc_mm_per_m", awc_low, awc_mid, awc_high, "soil provider low/high")
    factors = [
        awc,
        Factor("initial_soil_water_frac_taw", 0.25, 0.50, 0.75, "declared assumption (start state unknown)"),
        Factor("planting_shift_days", -14, 0, 14, "declared assumption within the planting window"),
    ]
    if allocation_mm is not None:
        factors.append(
            Factor(
                "irrigation_allocation_mm",
                allocation_mm * 0.8,
                allocation_mm,
                allocation_mm * 1.2,
                "declared assumption: +/-20 % around the farmer-confirmed value",
            )
        )
    return factors


def one_at_a_time(factors: Sequence[Factor]) -> list[dict[str, Any]]:
    """Baseline (all mid) plus each factor at low and high with the others at mid."""
    base = {f.name: f.mid for f in factors}
    scenarios = [{**base, "_label": "baseline"}]
    for f in factors:
        for level in ("low", "high"):
            scenarios.append({**base, f.name: getattr(f, level), "_label": f"{f.name}={level}"})
    return scenarios


def full_factorial(factors: Sequence[Factor]) -> list[dict[str, Any]]:
    combos = itertools.product(*[(("low", f.low), ("mid", f.mid), ("high", f.high)) for f in factors])
    out = []
    for combo in combos:
        sc = {f.name: v for f, (_, v) in zip(factors, combo, strict=True)}
        sc["_label"] = ",".join(f"{f.name}={lvl}" for f, (lvl, _) in zip(factors, combo, strict=True))
        out.append(sc)
    return out


@dataclass
class RankingReport:
    metric: str
    baseline_order: list[str]
    unchanged: int
    total: int
    flips: list[dict[str, Any]] = field(default_factory=list)  # scenario label + new order

    @property
    def sentence(self) -> str:
        drivers = sorted({k.split("=")[0] for f in self.flips for k in f["label"].split(",") if not k.endswith("=mid")})
        base = f"{self.metric}: ranking unchanged in {self.unchanged} of {self.total} combinations"
        return base + (f"; inputs involved in changes: {', '.join(drivers)}." if self.flips else ".")


def ranking_stability(
    run_fn: RunFn,
    scenarios: Sequence[dict[str, Any]],
    metrics: Mapping[str, bool],
) -> dict[str, RankingReport]:
    """``metrics`` maps metric name -> True if higher is better. The first scenario is the baseline."""
    results = [(sc["_label"], run_fn({k: v for k, v in sc.items() if k != "_label"})) for sc in scenarios]
    reports = {}
    for metric, higher_better in metrics.items():
        orders = [(label, _order(res, metric, higher_better)) for label, res in results]
        base = orders[0][1]
        flips = [{"label": label, "order": order} for label, order in orders[1:] if order != base]
        reports[metric] = RankingReport(
            metric, base, unchanged=len(orders) - len(flips), total=len(orders), flips=flips
        )
    return reports


def _order(result: Mapping[str, Mapping[str, float]], metric: str, higher_better: bool) -> list[str]:
    return sorted(result, key=lambda s: result[s][metric], reverse=higher_better)

/**
 * Pure helpers that turn API contracts into what the dashboard draws. No fetching, no React, so each
 * rule is unit-tested (src/live/model.test.ts).
 *
 * Rules kept here:
 * - Constraints filter (infeasible strategies are never ranked); priorities only order the feasible
 *   ones, by the metric of the higher-weighted priority, with the rule shown in words (no score).
 * - Paired differences come from the API (computed per weather path); nothing here subtracts medians.
 * - Results are "outdated" whenever the edits on screen differ from the request of the shown run.
 */
import type { MetricView, PairedDeltaView, Tone } from '../demo/figmaDemo'
import type {
  FarmerContext,
  PairedDelta,
  Result,
  RunDetail,
  RunRequest,
  SimulationMode,
  Strategy,
} from '../types/contracts'

export const MAX_SHIFT_DAYS = 14 // D6, mirrors contracts MAX_PLANTING_SHIFT_DAYS

export const METRICS: Record<string, { label: string; short: string }> = {
  irrigation_mm: { label: 'Irrigation need (net)', short: 'irrigation' },
  allocation_shortfall_days: { label: 'Days irrigation was short of the rule', short: 'shortfall days' },
  water_stress_days: { label: 'Water-stress days (model)', short: 'stress days' },
  aet_mm: { label: 'Actual evapotranspiration', short: 'actual ET' },
  deep_drainage_mm: { label: 'Deep drainage', short: 'drainage' },
  runoff_mm: { label: 'Runoff', short: 'runoff' },
  cover_days: { label: 'Crop cover days', short: 'cover days' },
  possible_low_cover_days: { label: 'Possible low-cover days', short: 'low-cover days' },
  crop_diversity_count: { label: 'Distinct crops', short: 'crops' },
}

export const TONES: Tone[] = ['baseline', 'water', 'soil']

export interface Draft {
  mode: SimulationMode
  allocationMm: number | null
  shifts: Record<string, number>
}

export interface Priorities {
  conserveWater: number
  protectSoil: number
}

export const draftFromRequest = (req: RunRequest | undefined, farmer?: FarmerContext | null): Draft => ({
  mode: req?.mode ?? 'irrigation_needed',
  allocationMm: req?.allocation_mm ?? farmer?.irrigation_allocation_mm ?? null,
  shifts: { ...(req?.planting_shift_days ?? {}) },
})

export function requestFromDraft(siteId: string, d: Draft): RunRequest {
  const shifts = Object.fromEntries(Object.entries(d.shifts).filter(([, v]) => v !== 0))
  return {
    site_id: siteId,
    mode: d.mode,
    allocation_mm: d.mode === 'fixed_allocation' ? d.allocationMm : null,
    planting_shift_days: shifts,
  }
}

/** Human-readable list of what differs between the shown run and the edits on screen. */
export function changesSince(
  run: RunDetail | null,
  d: Draft,
  names: Record<string, string>,
  farmerUpdatedAfterRun = false,
): string[] {
  if (!run) return []
  const out: string[] = []
  const req = run.request
  const reqMode = req.mode ?? 'irrigation_needed'
  if (reqMode !== d.mode) out.push('irrigation mode')
  else if (d.mode === 'fixed_allocation' && (req.allocation_mm ?? null) !== d.allocationMm) out.push('irrigation limit')
  const before = req.planting_shift_days ?? {}
  const ids = new Set([...Object.keys(before), ...Object.keys(d.shifts)])
  for (const id of ids) {
    if ((before[id] ?? 0) !== (d.shifts[id] ?? 0)) out.push(`planting date (${names[id] ?? id})`)
  }
  if (farmerUpdatedAfterRun) out.push('farm details')
  return out
}

/** Validation the API would apply; the UI disables Run with this message instead of sending it. */
export function draftProblem(d: Draft): string | null {
  if (d.mode === 'fixed_allocation' && (d.allocationMm == null || !(d.allocationMm >= 0)))
    return 'Enter an irrigation limit (mm per irrigated season) for fixed-allocation mode.'
  const bad = Object.entries(d.shifts).find(([, v]) => Math.abs(v) > MAX_SHIFT_DAYS)
  if (bad) return `Planting shifts are limited to ±${MAX_SHIFT_DAYS} days (D6).`
  return null
}

export const resultFor = (results: Result[], strategyId: string, metric: string) =>
  results.find((r) => r.strategy_id === strategyId && r.metric === metric)

export const isFeasible = (s: Strategy) => !s.feasibility || s.feasibility.feasible

export interface Ranking {
  order: Strategy[]
  excluded: Strategy[]
  rule: string
}

/**
 * Orders feasible strategies by the median of the metric tied to the higher-weighted priority
 * (conserve water -> irrigation need; protect soil -> possible low-cover days), ties broken by the
 * other. Infeasible strategies are excluded, never ranked.
 */
export function rankStrategies(strategies: Strategy[], results: Result[], p: Priorities): Ranking {
  const water = { metric: 'irrigation_mm', words: 'least irrigation need' }
  const soil = { metric: 'possible_low_cover_days', words: 'fewest possible low-cover days' }
  const [first, second] = p.conserveWater >= p.protectSoil ? [water, soil] : [soil, water]
  const feasible = strategies.filter(isFeasible)
  const excluded = strategies.filter((s) => !isFeasible(s))
  const p50 = (s: Strategy, m: string) => resultFor(results, s.id, m)?.p50 ?? Number.POSITIVE_INFINITY
  const order = [...feasible].sort(
    (a, b) => p50(a, first.metric) - p50(b, first.metric) || p50(a, second.metric) - p50(b, second.metric),
  )
  const rule =
    p.conserveWater === p.protectSoil
      ? `Priorities are equal, so options are ordered by ${first.words}, then ${second.words} (medians).`
      : `Ordered by ${first.words} (your higher priority), then ${second.words} (medians). No combined score is used.`
  return { order, excluded, rule }
}

const round = (v: number | null | undefined) => (v == null ? null : Math.round(v))

export function metricView(
  results: Result[],
  deltas: PairedDelta[],
  strategyId: string,
  metric: string,
): MetricView {
  const r = resultFor(results, strategyId, metric)
  const d = deltas.find((x) => x.strategy_id === strategyId && x.metric === metric)
  return {
    p50: round(r?.p50),
    p10: round(r?.p10),
    p90: round(r?.p90),
    paired: d ? pairedView(d) : null,
  }
}

export function pairedView(d: PairedDelta): PairedDeltaView {
  const better = (d.share_better ?? 0) >= (d.share_worse ?? 0)
  const short = METRICS[d.metric]?.short ?? d.metric
  const median = d.p50 ?? 0
  const word = median === 0 ? 'no median change in' : median > 0 ? 'more' : 'fewer'
  return {
    direction: better ? 'benefit' : 'disadvantage',
    label: `${word} ${short}`,
    medianDays: round(d.p50),
    p10Days: round(d.p10),
    p90Days: round(d.p90),
    betterPct: d.share_better == null ? null : Math.round(d.share_better * 100),
  }
}

/** Shared axis for range bars so strategies line up; padded 5 % and never inverted. */
export function axisFor(views: MetricView[]): [number, number] {
  const vals = views.flatMap((v) => [v.p10, v.p50, v.p90]).filter((v): v is number => v != null)
  if (vals.length === 0) return [0, 1]
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const pad = Math.max((hi - lo) * 0.05, 1)
  return [Math.max(0, Math.floor(lo - pad)), Math.ceil(hi + pad)]
}

export const yearsLabel = (years: number[]) => (years.length > 1 ? `${years[0]}–${years[years.length - 1]}` : `${years[0]}`)

/** Driest enabled replay window by total usable rain (null rain = unknown, never treated as dry). */
export function driestWindow(run: RunDetail) {
  const ok = run.replay_windows.filter((w) => w.enabled && w.rain_mm != null)
  return ok.length ? ok.reduce((a, b) => ((b.rain_mm as number) < (a.rain_mm as number) ? b : a)) : null
}

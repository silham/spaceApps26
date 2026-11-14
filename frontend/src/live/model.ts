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
  CropProfile,
  FarmerContext,
  ForecastOdds,
  PairedDelta,
  Result,
  RunDetail,
  RotationsUpdate,
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

/**
 * D16: a stored run was made on an older horizon or forecast than the outlook now shown (newer weather or a newer
 * seasonal forecast arrived), so its results are outdated until it is rerun.
 */
export function predictionChanged(
  run: RunDetail | null,
  outlook: { horizon_start: string; horizon_end: string; forecast_source_id?: string | null } | null,
): boolean {
  if (!run || !outlook) return false
  const iv = run.run.input_versions ?? {}
  const horizon = `${outlook.horizon_start} to ${outlook.horizon_end}`
  return iv.horizon !== horizon || (iv.forecast_source_id ?? null) !== (outlook.forecast_source_id ?? null)
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

// --------------------------------------------------------------------------- user-built rotations (D15)

/** The comparison period on the real calendar (D16), from GET /sites/{id}/horizon: planting must fall inside it. */
export interface Horizon {
  start: string
  end: string
}
export const MAX_ROTATIONS = 3 // mirrors contracts MAX_ROTATIONS
export const MAX_SEASONS = 4 // mirrors contracts MAX_SEASONS_PER_ROTATION

export interface SeasonDraft {
  crop_id: string
  plant_date: string
  irrigated: boolean
  usual_yield: string // text from the input; empty = not given
}
export interface RotationDraft {
  name: string
  seasons: SeasonDraft[]
}

export const blankSeason = (): SeasonDraft => ({ crop_id: '', plant_date: '', irrigated: false, usual_yield: '' })

const DAY_MS = 86_400_000
const parseDay = (iso: string) => Date.parse(`${iso}T00:00:00Z`)
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10)

/** Days from planting to maturity: the sum of the crop's FAO-56 stage lengths (null while any is missing). */
export function seasonDays(crop: CropProfile | undefined): number | null {
  if (!crop) return null
  const lengths = Object.values(crop.stage_lengths_days)
  if (lengths.length < 4 || lengths.some((l) => l.value == null)) return null
  return lengths.reduce((sum, l) => sum + (l.value as number), 0)
}

/** Harvest date as the server computes it: planting date plus the stage lengths. */
export function harvestDate(plantDate: string, crop: CropProfile | undefined): string | null {
  const days = seasonDays(crop)
  if (!plantDate || days == null || Number.isNaN(parseDay(plantDate))) return null
  return isoDay(parseDay(plantDate) + days * DAY_MS)
}

/** The first thing the API would refuse, in words; null when the rotations can be saved. */
export function rotationsProblem(
  rotations: RotationDraft[],
  crops: Map<string, CropProfile>,
  horizon: Horizon,
): string | null {
  const { start: first, end: last } = horizon
  if (rotations.length < 1 || rotations.length > MAX_ROTATIONS) return `Build 1 to ${MAX_ROTATIONS} rotations.`
  for (const [i, r] of rotations.entries()) {
    const where = `Rotation ${i + 1}`
    if (!r.name.trim()) return `${where}: give it a name.`
    if (r.seasons.length < 1) return `${where}: add at least one season.`
    const dated: { plant: string; end: string; n: number }[] = []
    for (const [j, s] of r.seasons.entries()) {
      const at = `${where}, season ${j + 1}`
      const crop = crops.get(s.crop_id)
      if (!crop) return `${at}: choose a crop.`
      if (!s.plant_date) return `${at}: choose a planting date.`
      if (s.plant_date < first || s.plant_date > last) return `${at}: planting must be between ${first} and ${last}.`
      const end = harvestDate(s.plant_date, crop)
      if (end == null) return `${at}: ${crop.name} has no complete growth-stage lengths.`
      if (end > last) return `${at}: ${crop.name} planted on ${s.plant_date} would be harvested ${end}, after the comparison ends (${last}).`
      if (s.usual_yield.trim() !== '') {
        const y = Number(s.usual_yield)
        if (!(y > 0 && y <= 30)) return `${at}: usual yield must be between 0 and 30 t/ha, or left empty.`
      }
      dated.push({ plant: s.plant_date, end, n: j + 1 })
    }
    dated.sort((a, b) => a.plant.localeCompare(b.plant))
    for (let k = 1; k < dated.length; k++) {
      const prev = dated[k - 1]!
      const cur = dated[k]!
      if (cur.plant <= prev.end) return `${where}: season ${cur.n} starts before season ${prev.n} is harvested (${prev.end}).`
    }
  }
  return null
}

/** Saved strategies turned back into editable drafts (so the builder opens with what is already stored). */
export function draftsFromStrategies(strategies: Strategy[]): RotationDraft[] {
  return strategies.map((s) => ({
    name: s.name,
    seasons: [...s.seasons]
      .filter((x) => x.crop_id != null)
      .sort((a, b) => a.plant_date.localeCompare(b.plant_date))
      .map((x) => ({
        crop_id: x.crop_id as string,
        plant_date: x.plant_date,
        irrigated: x.irrigation_rule != null,
        usual_yield: x.usual_yield_t_ha == null ? '' : String(x.usual_yield_t_ha),
      })),
  }))
}

export function rotationsRequest(rotations: RotationDraft[]): RotationsUpdate {
  // The generated type is a fixed-length tuple; rotationsProblem() has already enforced 1 to 3.
  const list = rotations.map((r) => ({
    name: r.name.trim(),
    seasons: r.seasons.map((s) => ({
      crop_id: s.crop_id,
      plant_date: s.plant_date,
      irrigated: s.irrigated,
      usual_yield_t_ha: s.usual_yield.trim() === '' ? null : Number(s.usual_yield),
    })),
  }))
  return { rotations: list as unknown as RotationsUpdate['rotations'] }
}

/** Per-season results of one metric (relative yield, t/ha), in season order. */
export const seasonResults = (results: Result[], strategyId: string, metric: string) =>
  results
    .filter((r) => r.strategy_id === strategyId && r.metric === metric && r.season_index != null)
    .sort((a, b) => (a.season_index as number) - (b.season_index as number))

// --------------------------------------------------------------------------- seasonal outlook (D16)

/** Below this the most likely tercile is not called a signal (equal odds are 1/3 each). Wording choice only. */
export const CLEAR_SIGNAL = 0.45

/** "Wetter than usual" style wording for the most likely tercile; "No clear signal" when odds stay near 1/3. */
export function oddsSummary(o: Pick<ForecastOdds, 'variable' | 'below' | 'near' | 'above'>): string {
  const words = o.variable === 'rain' ? ['drier', 'near normal', 'wetter'] : ['cooler', 'near normal', 'warmer']
  const probs = [o.below, o.near, o.above]
  const k = probs.indexOf(Math.max(...probs))
  const p = probs[k] ?? 0
  if (p < CLEAR_SIGNAL) return 'No clear signal'
  const share = `${Math.round(p * 100)}%`
  return k === 1 ? `${share} of members near normal` : `${share} of members ${words[k]} than usual`
}

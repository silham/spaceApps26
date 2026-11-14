/**
 * Narrow, defensive readers for the Data Journey chart payloads. The contract types `chart` as an
 * open dict, so each reader checks the shape it needs and returns null when the payload is not in the
 * documented form (the card then says so instead of drawing something wrong).
 * Shapes follow backend/src/ftm/data/journey.py, data/pipeline/run.py, validation/phenology.py and
 * validation/report.py.
 */
import type { JourneyStage } from '../types/contracts'

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v)
const isStr = (v: unknown): v is string => typeof v === 'string'
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const strArr = (v: unknown): string[] => (Array.isArray(v) ? v.filter(isStr) : [])

export interface CoverageSource { sourceId: string; product: string; start: string | null; end: string | null }
export interface RawCleanPoint { date: string; raw: number | null; processed: number | null; flag: string | null }
export interface Gap {
  variable: string; start: string; end: string; lengthDays: number | null
  resolved: boolean; method: string | null; whyUnresolved: string | null
}
export interface Season { start: string | null; peak: string; end: string | null; fallback: boolean }
export interface ViCurve {
  dates: string[]; ndviQa: (number | null)[]; ndviSmooth: (number | null)[]
  seasons: Season[]; lowCover: [string, string][]
}
export interface ValidationPoint { year: number; referenceDoy: number | null; detectedDoy: number | null; split: string }
export interface FootprintFeature { layer: string; label: string; properties: Obj; geometry: { type: string; coordinates: unknown } }

export const chartType = (s: JourneyStage): string | null => (isStr(s.chart?.type) ? s.chart.type : null)

export function readCoverage(s: JourneyStage): CoverageSource[] | null {
  const src = s.chart?.sources
  if (!Array.isArray(src)) return null
  return src.filter(isObj).map((r) => ({
    sourceId: String(r.source_id ?? ''),
    product: String(r.product ?? r.source_id ?? ''),
    start: isStr(r.coverage_start) ? r.coverage_start : null,
    end: isStr(r.coverage_end) ? r.coverage_end : null,
  }))
}

export function readMissing(s: JourneyStage): Record<string, string[]> | null {
  const series = s.chart?.series
  if (!isObj(series)) return null
  return Object.fromEntries(Object.entries(series).map(([k, v]) => [k, strArr(v)]))
}

export function readRawClean(s: JourneyStage): Record<string, RawCleanPoint[]> | null {
  const series = s.chart?.series
  if (!isObj(series)) return null
  const out: Record<string, RawCleanPoint[]> = {}
  for (const [name, rows] of Object.entries(series)) {
    if (!Array.isArray(rows)) continue
    out[name] = rows.filter(isObj).map((r) => ({
      date: String(r.date),
      raw: num(r.raw),
      processed: num(r.processed),
      flag: isStr(r.flag) ? r.flag : null,
    }))
  }
  return out
}

export function readGaps(s: JourneyStage): Gap[] | null {
  const gaps = s.chart?.gaps
  if (!Array.isArray(gaps)) return null
  return gaps.filter(isObj).map((g) => ({
    variable: String(g.variable),
    start: String(g.start),
    end: String(g.end),
    lengthDays: num(g.length_days),
    resolved: g.resolved === true,
    method: isStr(g.method) ? g.method : null,
    whyUnresolved: isStr(g.why_unresolved) ? g.why_unresolved : null,
  }))
}

export function readViCurve(s: JourneyStage): ViCurve | null {
  const c = s.chart
  if (!c || !Array.isArray(c.dates) || !Array.isArray(c.ndvi_smooth)) return null
  const series = (v: unknown) => (Array.isArray(v) ? v.map(num) : [])
  return {
    dates: strArr(c.dates),
    ndviQa: series(c.ndvi_qa),
    ndviSmooth: series(c.ndvi_smooth),
    seasons: (Array.isArray(c.seasons) ? c.seasons : []).filter(isObj).map((x) => ({
      start: isStr(x.start) ? x.start : null,
      peak: String(x.peak),
      end: isStr(x.end) ? x.end : null,
      fallback: x.fallback === true,
    })),
    lowCover: (Array.isArray(c.low_cover) ? c.low_cover : [])
      .filter((p): p is unknown[] => Array.isArray(p) && p.length === 2 && p.every(isStr))
      .map((p) => [p[0] as string, p[1] as string]),
  }
}

export function readValidation(s: JourneyStage): ValidationPoint[] | null {
  const pts = s.chart?.points
  if (!Array.isArray(pts)) return null
  return pts.filter(isObj).map((p) => ({
    year: Number(p.year),
    referenceDoy: num(p.reference_doy),
    detectedDoy: num(p.detected_doy),
    split: String(p.split ?? ''),
  }))
}

/** The footprint map payload is a FeatureCollection, either as the chart's `layers` or the chart itself. */
export function readFootprints(s: JourneyStage): FootprintFeature[] | null {
  const c = s.chart
  const fc = isObj(c?.layers) ? c.layers : c
  if (!isObj(fc) || !Array.isArray(fc.features)) return null
  return fc.features.filter(isObj).flatMap((f) => {
    const props = isObj(f.properties) ? f.properties : {}
    if (!isObj(f.geometry) || !isStr(props.layer)) return []
    return [{ layer: props.layer, label: String(props.label ?? props.layer), properties: props, geometry: f.geometry as { type: string; coordinates: unknown } }]
  })
}

export const detailStrings = (s: JourneyStage, key: string): string[] => strArr(s.details?.[key])

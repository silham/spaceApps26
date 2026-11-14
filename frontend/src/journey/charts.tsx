import { useMemo, useState } from 'react'
import type { JourneyStage } from '../types/contracts'
import { EChart, type EChartOption } from './EChart'
import {
  readCoverage, readGaps, readMissing, readRawClean, readValidation, readViCurve,
  type Gap,
} from './payloads'

// Colours are the dashboard tokens (styles/tokens.css); ECharts cannot read CSS variables.
const C = { text: '#4e5d55', grid: '#e2e7e3', primary: '#1e6b45', water: '#2f7fd8', warn: '#e59a0b', mute: '#85938b' }
const base = { textStyle: { fontFamily: 'Inter, system-ui, sans-serif', color: C.text }, animation: false }
const timeAxis = { type: 'time' as const, axisLine: { lineStyle: { color: C.grid } }, splitLine: { show: false } }
const valueAxis = { type: 'value' as const, splitLine: { lineStyle: { color: C.grid } } }
const catAxis = (data: string[]) => ({ type: 'category' as const, data, inverse: true, axisLine: { show: false }, axisTick: { show: false } })
const t = (d: string) => new Date(d).getTime()

const Empty = ({ children }: { children: string }) => <p className="muted small">{children}</p>
const Unreadable = () => <Empty>Chart data arrived in an unexpected form, so nothing is drawn.</Empty>

/** ECharts passes an untyped API object to custom renderers. */
type RenderApi = { value: (i: number) => unknown; coord: (p: unknown[]) => [number, number]; size: (p: [number, number]) => [number, number] }

/** A horizontal bar from value[1] to value[2] on the category given by value[0]. */
function barRenderer(fill: (value: unknown[]) => string) {
  return (_: unknown, api: unknown) => {
    const a = api as RenderApi
    const y = a.value(0)
    const x0 = a.coord([a.value(1), y])
    const x1 = a.coord([a.value(2), y])
    const h = a.size([0, 1])[1] * 0.5
    return {
      type: 'rect',
      shape: { x: x0[0], y: x0[1] - h / 2, width: Math.max(x1[0] - x0[0], 3), height: h },
      style: { fill: fill([a.value(0), a.value(1), a.value(2), a.value(3)]) },
    }
  }
}

/** Collect: one bar per source across the dates it covers. */
export function CoverageStrip({ stage }: { stage: JourneyStage }) {
  const rows = readCoverage(stage)
  const option = useMemo<EChartOption | null>(() => {
    if (!rows) return null
    const usable = rows.filter((r) => r.start)
    const now = Date.now()
    return {
      ...base,
      grid: { left: 170, right: 24, top: 8, bottom: 28 },
      tooltip: { trigger: 'item', formatter: (p: { data: { row: { product: string; start: string; end: string | null } } }) => `${p.data.row.product}<br/>${p.data.row.start} to ${p.data.row.end ?? 'ongoing'}` },
      xAxis: timeAxis,
      yAxis: catAxis(usable.map((r) => r.product)),
      series: [{
        type: 'custom',
        renderItem: barRenderer(() => C.water),
        encode: { x: [1, 2], y: 0 },
        data: usable.map((r) => ({ row: r, value: [r.product, t(r.start as string), r.end ? t(r.end) : now, 0] })),
      }],
    } as EChartOption
  }, [rows])
  if (!rows) return <Unreadable />
  if (rows.length === 0 || !option) return <Empty>No sources recorded.</Empty>
  return <EChart option={option} label={`Date coverage of ${rows.length} data sources`} height={Math.max(120, rows.length * 44 + 40)} />
}

/** Check: a tick for every date a variable is missing. Nothing is filled in. */
export function MissingTimeline({ stage }: { stage: JourneyStage }) {
  const series = readMissing(stage)
  const names = useMemo(() => (series ? Object.keys(series) : []), [series])
  const option = useMemo<EChartOption | null>(() => {
    if (!series) return null
    return {
      ...base,
      grid: { left: 110, right: 24, top: 8, bottom: 28 },
      tooltip: { trigger: 'item' },
      xAxis: timeAxis,
      yAxis: catAxis(names),
      series: [{ type: 'scatter', symbol: 'rect', symbolSize: [2, 14], itemStyle: { color: C.warn }, data: names.flatMap((n) => (series[n] ?? []).map((d) => [t(d), n])) }],
    } as EChartOption
  }, [series, names])
  if (!series || !option) return <Unreadable />
  const total = names.reduce((n, k) => n + (series[k]?.length ?? 0), 0)
  if (total === 0) return <Empty>No missing dates were found in the checked variables.</Empty>
  return <EChart option={option} label={`Missing dates per variable, ${total} in total`} height={Math.max(120, names.length * 34 + 50)} />
}

/** Clean: raw against processed for one variable at a time (units differ between variables). */
export function RawVsClean({ stage }: { stage: JourneyStage }) {
  const series = readRawClean(stage)
  const names = series ? Object.keys(series) : []
  const [pick, setPick] = useState('')
  const name = names.includes(pick) ? pick : (names[0] ?? '')
  const option = useMemo<EChartOption | null>(() => {
    if (!series || !name) return null
    const rows = series[name] ?? []
    return {
      ...base,
      grid: { left: 48, right: 24, top: 32, bottom: 28 },
      legend: { top: 0, right: 0 },
      tooltip: { trigger: 'axis' },
      xAxis: timeAxis,
      yAxis: valueAxis,
      series: [
        // A missing value stays a break in the line; it is never drawn as zero.
        { name: 'Raw', type: 'line', showSymbol: rows.length < 30, connectNulls: false, lineStyle: { color: C.mute, type: 'dashed' }, itemStyle: { color: C.mute }, data: rows.map((r) => [t(r.date), r.raw]) },
        { name: 'Processed', type: 'line', showSymbol: rows.length < 30, connectNulls: false, lineStyle: { color: C.primary }, itemStyle: { color: C.primary }, data: rows.map((r) => [t(r.date), r.processed]) },
        { name: 'Flagged', type: 'scatter', symbolSize: 8, itemStyle: { color: C.warn }, data: rows.filter((r) => r.flag).map((r) => [t(r.date), r.processed ?? r.raw]) },
      ],
    } as EChartOption
  }, [series, name])
  if (!series) return <Unreadable />
  if (!option) return <Empty>No variables in this payload.</Empty>
  const current = series[name] ?? []
  const flagged = current.filter((r) => r.flag)
  return (
    <>
      <label className="small row">
        Variable
        <select aria-label="Variable" value={name} onChange={(e) => setPick(e.target.value)}>
          {names.map((n) => <option key={n}>{n}</option>)}
        </select>
        <span className="muted">last {current.length} days</span>
      </label>
      <EChart option={option} label={`Raw and processed ${name}, ${flagged.length} flagged days`} />
      {flagged.length > 0 && <p className="small muted">Flagged: {flagged.map((r) => `${r.date} (${r.flag})`).join(', ')}</p>}
    </>
  )
}

/** Handle gaps: each gap as a bar; unresolved gaps look different and are explained in words. */
export function GapMarkers({ stage }: { stage: JourneyStage }) {
  const gaps = readGaps(stage)
  const vars = useMemo(() => (gaps ? [...new Set(gaps.map((g) => g.variable))] : []), [gaps])
  const option = useMemo<EChartOption | null>(() => {
    if (!gaps || gaps.length === 0) return null
    return {
      ...base,
      grid: { left: 110, right: 24, top: 8, bottom: 28 },
      tooltip: { trigger: 'item', formatter: (p: { data: { gap: Gap } }) => `${p.data.gap.variable}: ${p.data.gap.start} to ${p.data.gap.end}<br/>${p.data.gap.resolved ? `Estimated (${p.data.gap.method ?? 'method not recorded'})` : 'Left missing'}` },
      xAxis: timeAxis,
      yAxis: catAxis(vars),
      series: [{
        type: 'custom',
        renderItem: barRenderer((v) => (v[3] === 1 ? C.water : C.warn)),
        encode: { x: [1, 2], y: 0 },
        data: gaps.map((g) => ({ gap: g, value: [g.variable, t(g.start), t(g.end), g.resolved ? 1 : 0] })),
      }],
    } as EChartOption
  }, [gaps, vars])
  if (!gaps) return <Unreadable />
  if (gaps.length === 0 || !option) return <Empty>No gaps to handle.</Empty>
  return (
    <>
      <EChart option={option} label={`${gaps.length} data gaps, ${gaps.filter((g) => !g.resolved).length} left unresolved`} height={Math.max(120, vars.length * 40 + 50)} />
      <ul className="list list--tight small">
        {gaps.map((g, i) => (
          <li key={i}>
            <strong>{g.variable}</strong> {g.start} to {g.end}
            {g.lengthDays != null ? ` (${g.lengthDays} days)` : ''}:{' '}
            {g.resolved ? `estimated using ${g.method ?? 'a method that was not recorded'}` : `left missing. ${g.whyUnresolved ?? ''}`}
          </li>
        ))}
      </ul>
    </>
  )
}

/** Extract: smoothed greenness with suggested growing periods ("green-up"; never a planting date). */
export function ViCurveChart({ stage }: { stage: JourneyStage }) {
  const vi = readViCurve(stage)
  const option = useMemo<EChartOption | null>(() => {
    if (!vi) return null
    return {
      ...base,
      grid: { left: 44, right: 24, top: 32, bottom: 28 },
      legend: { top: 0, right: 0, data: ['Cloud-screened NDVI', 'Smoothed NDVI'] },
      tooltip: { trigger: 'axis' },
      xAxis: timeAxis,
      yAxis: { ...valueAxis, min: 0, max: 1 },
      series: [
        { name: 'Cloud-screened NDVI', type: 'scatter', symbolSize: 4, itemStyle: { color: C.mute }, data: vi.dates.map((d, i) => [t(d), vi.ndviQa[i] ?? null]).filter((p) => p[1] !== null) },
        {
          name: 'Smoothed NDVI', type: 'line', showSymbol: false, connectNulls: false, lineStyle: { color: C.primary, width: 2 }, itemStyle: { color: C.primary },
          data: vi.dates.map((d, i) => [t(d), vi.ndviSmooth[i] ?? null]),
          markArea: {
            silent: true,
            data: [
              ...vi.seasons.filter((s) => s.start && s.end).map((s) => [
                { xAxis: t(s.start as string), itemStyle: { color: s.fallback ? 'rgb(229 154 11 / 0.16)' : 'rgb(30 107 69 / 0.12)' } },
                { xAxis: t(s.end as string) },
              ]),
              ...vi.lowCover.map(([a, b]) => [{ xAxis: t(a), itemStyle: { color: 'rgb(133 147 139 / 0.22)' } }, { xAxis: t(b) }]),
            ],
          },
          markLine: { silent: true, symbol: 'none', lineStyle: { color: C.primary, type: 'dotted' }, label: { show: false }, data: vi.seasons.map((s) => ({ xAxis: t(s.peak) })) },
        },
      ],
    } as EChartOption
  }, [vi])
  if (!vi || !option) return <Unreadable />
  return (
    <>
      <EChart option={option} label={`Satellite greenness with ${vi.seasons.length} suggested growing periods`} height={260} />
      <ul className="list list--tight small">
        {vi.seasons.map((s, i) => (
          <li key={i}>
            Suggested growing period {i + 1}: green-up {s.start ?? 'not found'}, peak {s.peak}, end {s.end ?? 'not found'}
            {s.fallback && ' (too weak or cloudy; the local calendar is shown for this period instead)'}
          </li>
        ))}
        {vi.lowCover.length > 0 && (
          <li>Possible low vegetation cover: {vi.lowCover.map(([a, b]) => `${a} to ${b}`).join('; ')} (residue, cloud or crop type can also explain low greenness)</li>
        )}
      </ul>
    </>
  )
}

/** Validate: detected green-up day against the statewide reference planting day, by year. */
export function ObservedVsDetected({ stage }: { stage: JourneyStage }) {
  const pts = readValidation(stage)
  const option = useMemo<EChartOption | null>(() => {
    if (!pts) return null
    const series = (name: string, key: 'referenceDoy' | 'detectedDoy', color: string, symbol: string) => ({
      name, type: 'scatter', symbol, symbolSize: 10, itemStyle: { color },
      data: pts.filter((p) => p[key] != null).map((p) => [p.year, p[key]]),
    })
    return {
      ...base,
      grid: { left: 52, right: 24, top: 32, bottom: 32 },
      legend: { top: 0, right: 0 },
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value', min: (v: { min: number }) => v.min - 1, max: (v: { max: number }) => v.max + 1, interval: 1, splitLine: { show: false }, axisLabel: { formatter: (v: number) => String(v) } },
      yAxis: { ...valueAxis, name: 'day of year', scale: true },
      series: [series('Reference (statewide planting)', 'referenceDoy', C.water, 'circle'), series('Detected green-up', 'detectedDoy', C.primary, 'diamond')],
    } as EChartOption
  }, [pts])
  if (!pts || !option) return <Unreadable />
  const missed = pts.filter((p) => p.detectedDoy == null)
  return (
    <>
      <EChart option={option} label={`Reference and detected season-start day of year, ${pts.length} years`} />
      <p className="small muted">
        Tuning years: {pts.filter((p) => p.split === 'tuning').length} · development years: {pts.filter((p) => p.split === 'development').length}.
        {missed.length > 0 && ` No season detected in: ${missed.map((p) => p.year).join(', ')}.`}
      </p>
    </>
  )
}

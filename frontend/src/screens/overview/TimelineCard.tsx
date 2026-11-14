import { useMemo } from 'react'
import { EChart, type EChartOption } from '../../journey/EChart'
import { StateView } from '../../components/StateView'
import type { AsyncState } from '../../api/useAsync'
import type { EnvironmentalTimeline } from '../../types/contracts'

/**
 * Environmental timeline (guide §4 Observe): daily rain and temperature from one weather source and
 * quality-checked NDVI. Missing rain is drawn as a gap, never as zero. No Figma frame: card pattern.
 */
export function TimelineCard({ state }: { state: AsyncState<EnvironmentalTimeline> }) {
  const option = useMemo<EChartOption | null>(() => {
    if (state.status !== 'ready' || state.data.dates.length === 0) return null
    const t = state.data
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { top: 0, data: ['Rain (mm/day)', 'Max temp (°C)', 'Min temp (°C)', 'NDVI (QA passed)'] },
      grid: { left: 48, right: 48, top: 32, bottom: 28 },
      xAxis: { type: 'time' },
      yAxis: [
        { type: 'value', name: 'mm · °C', nameGap: 12 },
        { type: 'value', name: 'NDVI', min: 0, max: 1, splitLine: { show: false } },
      ],
      series: [
        { name: 'Rain (mm/day)', type: 'bar', data: t.dates.map((d, i) => [d, t.rain_mm[i] ?? null]), itemStyle: { color: '#2f7fd8' }, barMaxWidth: 3 },
        { name: 'Max temp (°C)', type: 'line', showSymbol: false, data: t.dates.map((d, i) => [d, t.tmax_c[i] ?? null]), lineStyle: { width: 1, color: '#e59a0b' }, itemStyle: { color: '#e59a0b' } },
        { name: 'Min temp (°C)', type: 'line', showSymbol: false, data: t.dates.map((d, i) => [d, t.tmin_c[i] ?? null]), lineStyle: { width: 1, color: '#85938b' }, itemStyle: { color: '#85938b' } },
        { name: 'NDVI (QA passed)', type: 'line', yAxisIndex: 1, connectNulls: false, data: (t.vegetation_dates ?? []).map((d, i) => [d, t.ndvi?.[i] ?? null]), lineStyle: { color: '#2e9b57' }, itemStyle: { color: '#2e9b57' } },
      ],
    } as EChartOption
  }, [state])

  const t = state.status === 'ready' ? state.data : null
  const missingRain = t ? t.rain_mm.filter((v) => v == null).length : 0
  return (
    <section className="card page-card" aria-labelledby="timeline-h">
      <div className="card-title card-title--small">
        <h2 id="timeline-h">Field history</h2>
        <p>Daily weather and satellite greenness for the last years on record. Gaps are missing values, not zeros.</p>
      </div>
      {state.status === 'loading' && <StateView kind="loading" />}
      {state.status === 'error' && <StateView kind="failed" title="History could not be loaded">{state.error.message}</StateView>}
      {t && t.dates.length === 0 && <StateView kind="missing">{t.vegetation_note ?? 'No weather is stored for this farm.'}</StateView>}
      {option && t && (
        <>
          <EChart option={option} height={260} label={`Daily rain, temperature and NDVI ${t.start} to ${t.end}`} />
          <p className="small muted">
            {t.start} to {t.end} · {missingRain} day(s) without usable rain · {t.vegetation_note ?? ''} Sources:{' '}
            {t.source_ids.join(', ')}
            {t.processing_run_id ? ` · processing run ${t.processing_run_id}` : ''}
            {t.vegetation_source_id ? '' : ' · satellite vegetation not loaded'}
          </p>
        </>
      )}
    </section>
  )
}

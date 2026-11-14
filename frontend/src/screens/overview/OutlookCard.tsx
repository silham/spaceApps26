import { useMemo } from 'react'
import { EChart, type EChartOption } from '../../journey/EChart'
import { StateView } from '../../components/StateView'
import type { AsyncState } from '../../api/useAsync'
import { oddsSummary } from '../../live/model'
import type { ForecastOdds, OutlookBand, WeatherOutlook } from '../../types/contracts'

const pct = (v: number) => `${Math.round(v * 100)}%`

function band(name: string, dates: string[], b: OutlookBand, color: string, stack: string): EChartOption['series'] {
  const lo = b.p10.map((v, i) => [dates[i], v])
  const width = b.p90.map((v, i) => [dates[i], v == null || b.p10[i] == null ? null : v - (b.p10[i] as number)])
  return [
    // stackStrategy 'all': a band below 0 (winter minimum temperatures) must stack like one above it
    { name: `${name} p10`, type: 'line', stack, stackStrategy: 'all', data: lo, showSymbol: false, lineStyle: { opacity: 0 }, tooltip: { show: false } },
    {
      name: `${name} range`,
      type: 'line',
      stack,
      stackStrategy: 'all',
      data: width,
      showSymbol: false,
      lineStyle: { opacity: 0 },
      areaStyle: { color, opacity: 0.18 },
      tooltip: { show: false },
    },
    {
      name,
      type: 'line',
      data: b.p50.map((v, i) => [dates[i], v]),
      showSymbol: false,
      lineStyle: { color, width: 2 },
      itemStyle: { color },
    },
  ] as EChartOption['series']
}

/**
 * The coming months (D16): seasonal-forecast odds, today's simulated soil water and bands from past NASA POWER years
 * weighted by those odds. No Figma frame: card pattern of the Field history card.
 */
export function OutlookCard({ state, onEditFieldNow }: { state: AsyncState<WeatherOutlook>; onEditFieldNow: () => void }) {
  const o = state.status === 'ready' ? state.data : null
  const water = useMemo<EChartOption | null>(() => {
    if (!o || o.dates.length === 0) return null
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { top: 0, data: ['Soil water (simulated)', 'Rain from today'] },
      grid: { left: 52, right: 16, top: 32, bottom: 28 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', name: 'mm', nameGap: 12 },
      series: [
        ...(band('Soil water (simulated)', o.dates, o.storage_mm, '#2e9b57', 'sw') as object[]),
        ...(band('Rain from today', o.dates, o.rain_cumulative_mm, '#2f7fd8', 'rain') as object[]),
        {
          name: 'Soil water capacity',
          type: 'line',
          data: [
            [o.dates[0], o.soil_water_capacity_mm],
            [o.dates[o.dates.length - 1], o.soil_water_capacity_mm],
          ],
          showSymbol: false,
          lineStyle: { type: 'dashed', color: '#85938b', width: 1 },
          tooltip: { show: false },
        },
      ],
    } as EChartOption
  }, [o])
  const temps = useMemo<EChartOption | null>(() => {
    if (!o || o.dates.length === 0) return null
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { top: 0, data: ['Max temp', 'Min temp'] },
      grid: { left: 52, right: 16, top: 32, bottom: 28 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', name: '°C', nameGap: 12 },
      series: [
        ...(band('Max temp', o.dates, o.tmax_c, '#e59a0b', 'tx') as object[]),
        ...(band('Min temp', o.dates, o.tmin_c, '#5b6ee1', 'tn') as object[]),
      ],
    } as EChartOption
  }, [o])

  const windows = o ? [...new Set(o.odds.map((x) => x.window))] : []
  return (
    <section className="card page-card outlook" aria-labelledby="outlook-h">
      <div className="card-title card-title--small">
        <h2 id="outlook-h">The coming months</h2>
        <p>
          Seasonal forecast odds, today&rsquo;s simulated soil water, and the range of past years made more or less likely
          by the forecast. Forecast odds, not a guarantee.
        </p>
      </div>
      {state.status === 'loading' && <StateView kind="loading" title="Preparing the outlook…" />}
      {state.status === 'error' && (
        <StateView kind="failed" title="The outlook could not be prepared">
          {state.error.message}
        </StateView>
      )}
      {o && (
        <>
          <div className="outlook__now">
            <div>
              <span className="small muted">Soil water now (simulated, {o.observed_end})</span>
              <strong>
                {Math.round(o.soil_water_now_mm)} of {Math.round(o.soil_water_capacity_mm)} mm
              </strong>
              <meter
                min={0}
                max={o.soil_water_capacity_mm}
                value={o.soil_water_now_mm}
                aria-label="Soil water now as a share of capacity"
              />
            </div>
            <p className="small muted">
              {o.soil_water_now_mm >= 0.9 * o.soil_water_capacity_mm && /bare fallow/.test(o.initial_assumption)
                ? 'In the model, bare soil loses water only from its top layer, so a year of bare soil keeps the profile near full: read this as an upper value. '
                : ''}
              {o.initial_assumption}{' '}
              <button type="button" className="link" onClick={onEditFieldNow}>
                Tell us what is on the field
              </button>
            </p>
          </div>

          {windows.length > 0 ? (
            <table className="outlook__odds">
              <caption className="small muted">
                Share of the {o.odds[0]?.member_count} forecast members below / near / above normal for each period (not
                calibrated probabilities)
              </caption>
              <thead>
                <tr>
                  <th scope="col">Period</th>
                  <th scope="col">Rain</th>
                  <th scope="col">Temperature</th>
                </tr>
              </thead>
              <tbody>
                {windows.map((w) => {
                  const rain = o.odds.find((x) => x.window === w && x.variable === 'rain')
                  const temp = o.odds.find((x) => x.window === w && x.variable === 'temperature')
                  const cell = (x: ForecastOdds | undefined) =>
                    x ? (
                      <>
                        <strong>{oddsSummary(x)}</strong>
                        <span className="small muted">
                          {' '}
                          ({pct(x.below)} / {pct(x.near)} / {pct(x.above)})
                        </span>
                      </>
                    ) : (
                      '—'
                    )
                  return (
                    <tr key={w}>
                      <th scope="row">{w}</th>
                      <td>{cell(rain)}</td>
                      <td>{cell(temp)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <StateView kind="unavailable" title="No seasonal forecast for this farm yet">
              Every past year is equally likely until a forecast is loaded.
            </StateView>
          )}

          {water && (
            <EChart option={water} height={220} label={`Simulated soil water and rain from ${o.dates[0]}, ${o.range_label}`} />
          )}
          {temps && <EChart option={temps} height={200} label={`Daily temperature range from ${o.dates[0]}`} />}
          <p className="small muted">
            Shaded: {o.range_label} over {o.n_paths} weather paths drawn from past years
            {o.effective_sample_size != null ? ` (about ${Math.round(o.effective_sample_size)} effective past years)` : ''}
            . Comparison period {o.horizon_start} to {o.horizon_end}. Sources: {o.source_ids.join(', ')}.
          </p>
          {o.attribution && (
            <p className="small muted">
              <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
                Weather data by Open-Meteo.com
              </a>{' '}
              (ECMWF SEAS5, CC BY 4.0).
            </p>
          )}
          <details className="small">
            <summary>How this is made</summary>
            <ul>
              {[...(o.assumptions ?? []), ...(o.limitations ?? [])].map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  )
}

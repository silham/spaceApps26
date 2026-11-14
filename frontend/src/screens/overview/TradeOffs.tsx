import { useMemo } from 'react'
import { EChart, type EChartOption } from '../../journey/EChart'
import { METRICS, TONES, isFeasible, resultFor, type Ranking } from '../../live/model'
import type { Result, Strategy } from '../../types/contracts'

const COLORS = { baseline: '#4a5a51', water: '#2f7fd8', soil: '#2e9b57' } as const
const X = 'irrigation_mm'
const Y = 'possible_low_cover_days'

/**
 * Trade-off view (guide §3 "trade-off scatter"; cut path: table). Each strategy is its median with
 * the central 80% simulation range as whiskers on both axes; the table below carries the same numbers.
 * No Figma frame: card pattern.
 */
export function TradeOffs({
  strategies,
  results,
  ranking,
  outdated,
}: {
  strategies: Strategy[]
  results: Result[]
  ranking: Ranking
  outdated: boolean
}) {
  const option = useMemo<EChartOption>(() => {
    const series = strategies.flatMap((s, i) => {
      const x = resultFor(results, s.id, X)
      const y = resultFor(results, s.id, Y)
      if (!isFeasible(s) || x?.p50 == null || y?.p50 == null) return []
      const color = COLORS[TONES[i] ?? 'baseline']
      const name = s.name.split(':')[0]
      const whisker = (pts: [number | null | undefined, number | null | undefined][]) =>
        pts.every(([a, b]) => a != null && b != null)
          ? [{ name, type: 'line', data: pts, showSymbol: false, lineStyle: { color, width: 2 }, tooltip: { show: false } }]
          : []
      return [
        { name, type: 'scatter', symbolSize: 14, itemStyle: { color }, data: [[x.p50, y.p50]] },
        ...whisker([[x.p10, y.p50], [x.p90, y.p50]]),
        ...whisker([[x.p50, y.p10], [x.p50, y.p90]]),
      ]
    })
    return {
      animation: false,
      legend: { top: 0, data: strategies.filter(isFeasible).map((s) => s.name.split(':')[0]) },
      tooltip: { trigger: 'item', formatter: (p: { seriesName: string; value: number[] }) => `${p.seriesName}<br/>irrigation ${Math.round(p.value[0] ?? 0)} mm · low-cover ${Math.round(p.value[1] ?? 0)} days` },
      grid: { left: 64, right: 24, top: 36, bottom: 48 },
      xAxis: { type: 'value', name: `${METRICS[X]?.label} (mm)`, nameLocation: 'middle', nameGap: 28, scale: true },
      yAxis: { type: 'value', name: `${METRICS[Y]?.label} (days)`, nameLocation: 'middle', nameGap: 44, scale: true },
      series,
    } as EChartOption
  }, [strategies, results])

  return (
    <section className="card page-card" aria-labelledby="tradeoffs-h" id="tradeoffs">
      <div className="card-title">
        <h2 id="tradeoffs-h">Trade-offs: water versus soil protection</h2>
        <p>Lower-left is less irrigation and fewer possible low-cover days. Dots are medians; lines the central 80% simulation range.</p>
      </div>
      {outdated && <p className="small muted">These are the last run's results; your edits are not included until you rerun.</p>}
      <EChart option={option} height={300} label="Scatter of irrigation need against possible low-cover days for each strategy" />
      <div>
        <h3>Your options in priority order</h3>
        <p className="small muted">{ranking.rule}</p>
        <ol className="ranking">
          {ranking.order.map((s) => (
            <li key={s.id}>{s.name}</li>
          ))}
        </ol>
        {ranking.excluded.length > 0 && (
          <p className="small">
            Not ranked (breaks a hard constraint): {ranking.excluded.map((s) => `${s.name} — ${s.feasibility?.reasons?.join('; ')}`).join(' · ')}
          </p>
        )}
      </div>
      <div className="table-wrap">
        <table className="metrics-table">
          <caption className="sr-only">All metrics, median and central 80% simulation range</caption>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              {strategies.map((s) => (
                <th key={s.id} scope="col">
                  {s.name.split(':')[0]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(METRICS).map(([m, meta]) => {
              const any = strategies.some((s) => resultFor(results, s.id, m))
              if (!any) return null
              return (
                <tr key={m}>
                  <th scope="row">
                    {meta.label} ({resultFor(results, strategies[0]?.id ?? '', m)?.unit})
                  </th>
                  {strategies.map((s) => {
                    const r = resultFor(results, s.id, m)
                    return (
                      <td key={s.id} className="num">
                        {r?.p50 == null
                          ? 'not simulated'
                          : `${Math.round(r.p50)} (${r.p10 == null ? '—' : Math.round(r.p10)}–${r.p90 == null ? '—' : Math.round(r.p90)})`}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

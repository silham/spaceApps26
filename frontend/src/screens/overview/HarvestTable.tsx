import { isFeasible, seasonResults } from '../../live/model'
import type { CropProfile, Result, Strategy } from '../../types/contracts'

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v)}%`)
const tonnes = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(1))
const range = (r: Result | undefined, f: (v: number | null | undefined) => string) =>
  r && r.p10 != null && r.p90 != null ? `${f(r.p10)} – ${f(r.p90)}` : 'not reported'

/**
 * Harvest per crop season: water-limited relative yield (FAO-33) with its central 80% simulation range, and tonnes
 * per hectare only where the farmer entered a usual yield. No Figma frame: card and table patterns.
 */
export function HarvestTable({
  strategies,
  results,
  crops,
  outdated,
}: {
  strategies: Strategy[]
  results: Result[]
  crops: Map<string, CropProfile>
  outdated: boolean
}) {
  const withYield = strategies.filter((s) => isFeasible(s) && seasonResults(results, s.id, 'relative_yield_pct').length)
  if (withYield.length === 0) return null
  return (
    <section className="card page-card" aria-labelledby="harvest-h">
      <div className="card-title">
        <h2 id="harvest-h">Harvest (water-limited)</h2>
        <p>
          Share of the water-unlimited yield each crop keeps once water stress is counted (FAO-33). It ignores nutrients, pests,
          heat, frost and variety, so read it as a comparison between rotations, not a forecast.
        </p>
      </div>
      {outdated && <p className="run-error">Results outdated: rerun the comparison before relying on these numbers.</p>}
      <div className="table-wrap">
        <table className="metrics-table">
          <thead>
            <tr>
              <th scope="col">Rotation</th>
              <th scope="col">Season and crop</th>
              <th scope="col">Relative yield, median</th>
              <th scope="col">Central 80% simulation range</th>
              <th scope="col">Your usual yield scaled (t/ha)</th>
            </tr>
          </thead>
          <tbody>
            {withYield.flatMap((s) => {
              const rel = seasonResults(results, s.id, 'relative_yield_pct')
              const tha = seasonResults(results, s.id, 'yield_t_ha')
              return rel.map((r, k) => {
                const t = tha.find((x) => x.season_index === r.season_index)
                return (
                  <tr key={`${s.id}-${r.season_index}`}>
                    {k === 0 && (
                      <th scope="row" rowSpan={rel.length}>
                        {s.name}
                        {s.is_baseline && <span className="muted small"> · current practice</span>}
                      </th>
                    )}
                    <td>
                      {(r.season_index ?? 0) + 1}. {crops.get(r.crop_id ?? '')?.name ?? r.crop_id}
                    </td>
                    <td className="num">{pct(r.p50)}</td>
                    <td className="num">{range(r, pct)}</td>
                    <td className="num">
                      {t ? (
                        <>
                          {tonnes(t.p50)} <span className="muted small">({range(t, tonnes)}; from your usual yield)</span>
                        </>
                      ) : (
                        <span className="muted">not entered</span>
                      )}
                    </td>
                  </tr>
                )
              })
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

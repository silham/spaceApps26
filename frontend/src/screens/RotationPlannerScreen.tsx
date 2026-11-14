import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { AsyncView } from '../components/AsyncView'
import { DemoBadge } from '../components/DemoBadge'
import { Badge } from '../components/ui'

/**
 * Rotation planner: the strategies the API holds for the site, with season dates and feasibility.
 * No Figma frame exists for this view yet; it reuses the dashboard's card and badge patterns.
 */
export function RotationPlannerScreen({ siteId }: { siteId: string | undefined }) {
  const strategies = useAsync(
    () => (siteId ? api.strategies(siteId) : Promise.reject(new Error('no site is available from the API'))),
    [siteId],
  )
  return (
    <>
      <h1 className="page-title">Rotation planner</h1>
      <section className="card page-card" aria-labelledby="planner-h">
        <h2 id="planner-h">Strategies for this farm</h2>
        <AsyncView state={strategies} isEmpty={(d) => d.length === 0}>
          {(data) => (
            <ul className="list">
              {data.map((s) => (
                <li key={s.id}>
                  <div className="row">
                    <h3>{s.name}</h3>
                    {s.is_baseline && <Badge tone="neutral" dot={false}>Current practice</Badge>}
                    {s.is_demo && <DemoBadge />}
                  </div>
                  <div className="row">
                    {s.seasons.map((season, i) => (
                      <span key={season.plant_date} className="chip">
                        Season {i + 1}: {season.crop_id ?? 'Fallow'} · {season.plant_date} → {season.end_date}
                      </span>
                    ))}
                  </div>
                  {s.feasibility && !s.feasibility.feasible && (
                    <p role="note" className="alert">
                      ⚠ Not feasible: {s.feasibility.reasons?.join('; ') || 'no reason recorded'}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </AsyncView>
      </section>
    </>
  )
}

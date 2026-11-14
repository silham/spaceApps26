import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { AsyncView } from '../components/AsyncView'
import { DemoBadge } from '../components/DemoBadge'

/** Experiment: three aligned rotation rows, constraints vs priorities, replay. TODO(M2): build per Figma. */
export function ExperimentScreen({ siteId }: { siteId: string }) {
  const strategies = useAsync(() => api.strategies(siteId), [siteId])
  return (
    <section aria-labelledby="experiment-h">
      <h2 id="experiment-h">Experiment</h2>
      <AsyncView state={strategies} isEmpty={(d) => d.length === 0}>
        {(data) => (
          <ol>
            {data.map((s) => (
              <li key={s.id}>
                <strong>{s.name}</strong> {s.is_baseline && '(current practice)'} {s.is_demo && <DemoBadge />}
                <div>
                  {s.seasons.map((season) => `${season.plant_date} → ${season.end_date}`).join('  |  ')}
                </div>
                {s.feasibility && !s.feasibility.feasible && (
                  <div role="note">Not feasible: {s.feasibility.reasons?.join('; ')}</div>
                )}
              </li>
            ))}
          </ol>
        )}
      </AsyncView>
    </section>
  )
}

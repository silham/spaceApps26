import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { AsyncView } from '../components/AsyncView'
import { DemoBadge } from '../components/DemoBadge'
import { RangeBar } from '../components/RangeBar'

/** Decide: strategy cards with ranges, trade-offs, decision card. TODO(M2): build per Figma. */
export function DecideScreen({ runId }: { runId: string }) {
  const results = useAsync(() => api.results(runId), [runId])
  return (
    <section aria-labelledby="decide-h">
      <h2 id="decide-h">Decide</h2>
      <AsyncView state={results} isEmpty={(d) => d.length === 0}>
        {(data) => (
          <ul>
            {data.map((r) => (
              <li key={r.id}>
                {r.strategy_id} · {r.metric}: <RangeBar result={r} /> {r.is_demo && <DemoBadge />}
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
    </section>
  )
}

import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { AsyncView } from '../components/AsyncView'
import { DemoBadge } from '../components/DemoBadge'
import { RangeBar } from '../components/RangeBar'
import { SourceLabel } from '../components/SourceLabel'

/**
 * Evidence & validation: the source register and the stored results for the run. No Figma frame
 * exists for this view yet; it reuses the dashboard's card pattern.
 */
export function EvidenceScreen({ runId }: { runId: string }) {
  const sources = useAsync(api.sources, [])
  const results = useAsync(() => api.results(runId), [runId])
  return (
    <>
      <h1 className="page-title">Evidence &amp; validation</h1>
      <section className="card" aria-labelledby="sources-h">
        <h2 id="sources-h">Sources used</h2>
        <AsyncView state={sources}>{(data) => <SourceLabel sources={data} />}</AsyncView>
      </section>
      <section className="card" aria-labelledby="results-h">
        <h2 id="results-h">Results for run {runId}</h2>
        <AsyncView state={results} isEmpty={(d) => d.length === 0}>
          {(data) => (
            <ul className="list">
              {data.map((r) => (
                <li key={r.id}>
                  <div className="row">
                    <span>
                      {r.strategy_id} · {r.metric}: <RangeBar result={r} />
                    </span>
                    {r.is_demo && <DemoBadge />}
                  </div>
                  <span className="small muted">Sources: {r.source_ids.join(', ') || 'none recorded'}</span>
                </li>
              ))}
            </ul>
          )}
        </AsyncView>
      </section>
      <section className="card" aria-labelledby="validation-h">
        <h2 id="validation-h">Validation</h2>
        <p>
          The API does not serve validation results yet, so range coverage has not been evaluated. Ranges are a
          central 80% simulation range (p10–p90), not a prediction interval.
        </p>
      </section>
    </>
  )
}

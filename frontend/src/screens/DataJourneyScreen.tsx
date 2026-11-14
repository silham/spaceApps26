import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { DemoBadge } from '../components/DemoBadge'
import { Badge } from '../components/ui'
import { KIND_TONE, STAGES, STATUS } from '../journey'

/**
 * Data Journey: nine stage cards. No Figma frame exists for this view yet; it reuses the
 * dashboard's card and status-badge patterns. Stages the API does not report show "Unavailable".
 */
export function DataJourneyScreen({ siteId }: { siteId: string | undefined }) {
  const journey = useAsync(
    () => (siteId ? api.journey(siteId) : Promise.reject(new Error('no site is available from the API'))),
    [siteId],
  )
  const stages = journey.status === 'ready' ? journey.data : []
  return (
    <>
      <h1 className="page-title">Data Journey</h1>
      {journey.status === 'loading' && <p role="status">Loading pipeline status…</p>}
      {journey.status === 'error' && (
        <p role="alert" className="alert">
          ⚠ Pipeline status could not be loaded: {journey.error.message}
        </p>
      )}
      <ol className="stage-grid">
        {STAGES.map((stage) => {
          const payload = stages.find((s) => s.stage === stage.id)
          const status = STATUS[payload?.status ?? 'unavailable']
          return (
            <li key={stage.id} className="card page-card">
              <div className="row">
                <h2>{stage.label}</h2>
                <Badge tone={KIND_TONE[status.kind]}>{status.label}</Badge>
                {payload?.is_demo && <DemoBadge />}
              </div>
              <p className="muted">{stage.question}</p>
              {payload && <p>{payload.summary}</p>}
              {payload && (
                <p className="small muted">
                  Sources: {payload.source_ids?.join(', ') || 'none recorded'}
                  {payload.processing_run_id ? ` · run ${payload.processing_run_id}` : ''}
                </p>
              )}
            </li>
          )
        })}
      </ol>
    </>
  )
}

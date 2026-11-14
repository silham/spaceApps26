import { ctl } from '../../components/ctl'
import { STAGES, STATUS } from '../../journey'
import type { JourneyStageName, StageStatus } from '../../types/contracts'

/** "Previous run · Data Journey": the nine pipeline stages as status chips (Figma node 3:74). */
export function JourneySummary({
  statuses,
  illustrative,
  onInspect,
}: {
  statuses: [JourneyStageName, StageStatus][]
  illustrative: boolean
  onInspect: () => void
}) {
  const byStage = new Map(statuses)
  return (
    <section className="card" aria-labelledby="journey-summary-h">
      <div className="section-title">
        <h2 id="journey-summary-h">Previous run · Data Journey</h2>
        <button type="button" className="link" onClick={onInspect}>
          Inspect pipeline →
        </button>
      </div>
      <div className="stages">
        {STAGES.map((stage) => {
          const status = STATUS[byStage.get(stage.id) ?? 'unavailable']
          return (
            <button
              key={stage.id}
              type="button"
              className={ctl(status.warn ? 'warning' : 'outline')}
              onClick={onInspect}
            >
              <span aria-hidden="true">{status.glyph} </span>
              {stage.label}
              {'\n'}
              {status.label}
            </button>
          )
        })}
      </div>
      <p className="small muted">
        {illustrative
          ? 'Illustrative statuses — populated from pipeline output for the selected period.'
          : 'Statuses from pipeline output for the selected period.'}
      </p>
    </section>
  )
}

import alertIcon from '../../assets/v2/icon-alert-14.svg'
import checkIcon from '../../assets/v2/icon-check-14.svg'
import { Badge, Icon } from '../../components/ui'
import { STAGES, STATUS } from '../../journey'
import type { JourneyStageName, StageStatus } from '../../types/contracts'

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** "Previous run · Data Journey": the nine pipeline stages as a status stepper (Figma node 25:202). */
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
  const steps = STAGES.map((stage) => ({ ...stage, status: byStage.get(stage.id) ?? ('unavailable' as StageStatus) }))
  const count = (...wanted: StageStatus[]) => steps.filter((s) => wanted.includes(s.status)).length
  const passed = count('ok')
  const warnings = count('warning')
  const failed = count('failed')
  const notStarted = count('not_started')
  const unavailable = count('unavailable')

  return (
    <section className="card" aria-labelledby="journey-summary-h">
      <div className="card-head">
        <div className="card-title card-title--small">
          <h2 id="journey-summary-h">Previous run · Data Journey</h2>
          <p>
            {illustrative
              ? 'Illustrative statuses — populated from pipeline output for the selected period.'
              : 'Statuses from pipeline output for the selected period.'}
          </p>
        </div>
        {passed > 0 && <Badge tone="success">{passed} passed</Badge>}
        {warnings > 0 && <Badge tone="warning">{plural(warnings, 'warning')}</Badge>}
        {failed > 0 && <Badge tone="warning">{failed} failed</Badge>}
        {notStarted > 0 && <Badge tone="neutral">{notStarted} not started</Badge>}
        {unavailable > 0 && <Badge tone="neutral">{unavailable} unavailable</Badge>}
        <button type="button" className="btn btn--secondary" onClick={onInspect}>
          Inspect pipeline →
        </button>
      </div>
      <div className="steps">
        {steps.map((step, i) => {
          const { label, kind } = STATUS[step.status]
          // A connector is "done" only when both stages it joins have run.
          const ran = (j: number) => {
            const other = steps[j]
            return other !== undefined && STATUS[other.status].kind !== 'idle'
          }
          const line = (j: number) => `step__line${ran(i) && ran(j) ? ' step__line--done' : ''}`
          return (
            <button key={step.id} type="button" className="step" onClick={onInspect}>
              <span className="step__track">
                <span className={i > 0 ? line(i - 1) : 'step__line step__line--end'} />
                <span className={`step__dot step__dot--${kind}`}>
                  {kind === 'ok' && <Icon src={checkIcon} size={14} />}
                  {kind === 'warning' && <Icon src={alertIcon} size={14} />}
                </span>
                <span className={i < steps.length - 1 ? line(i + 1) : 'step__line step__line--end'} />
              </span>
              <span className="step__index" aria-hidden="true">Step {i + 1}</span>
              <span className="step__name">{step.label}</span>
              <span className={`step__status step__status--${kind}`}>{label}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

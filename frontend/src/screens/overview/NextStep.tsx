import { useState } from 'react'
import { apiUrl } from '../../api/client'
import downloadIcon from '../../assets/v2/icon-download.svg'
import lockIcon from '../../assets/v2/icon-lock.svg'
import { Icon, SelectControl } from '../../components/ui'
import type { DecisionCard } from '../../types/contracts'

const RERUN = 'Rerun comparison before choosing and exporting.'

type ExportState = { status: 'idle' } | { status: 'saving' } | { status: 'failed'; message: string } | { status: 'done'; card: DecisionCard }

/**
 * "Choose your next step" (Figma node 28:467). Choosing and exporting stay disabled while the
 * results are outdated, so a decision card can never be built on stale numbers.
 */
export function NextStep({
  strategies,
  outdated,
  lockReason,
  onExport,
}: {
  strategies: readonly { id: string; name: string }[]
  outdated: boolean
  /** Why choosing is locked when there is no current run (overrides the rerun message). */
  lockReason?: string
  /** Live mode: records the decision and returns the exported card. */
  onExport?: (strategyId: string, reason: string) => Promise<DecisionCard>
}) {
  const [chosen, setChosen] = useState('')
  const [reason, setReason] = useState('')
  const [exp, setExp] = useState<ExportState>({ status: 'idle' })
  const locked = outdated || Boolean(lockReason)
  const lockText = lockReason ?? RERUN
  const canExport = !locked && chosen !== '' && reason.trim() !== '' && exp.status !== 'saving' && Boolean(onExport)
  const doExport = () => {
    if (!onExport) return
    setExp({ status: 'saving' })
    onExport(chosen, reason.trim()).then(
      (card) => setExp({ status: 'done', card }),
      (e: Error) => setExp({ status: 'failed', message: e.message }),
    )
  }

  return (
    <section className="card next" aria-labelledby="next-h">
      <div className="card-title">
        <h2 id="next-h">Choose your next step</h2>
        <p>Pick a strategy, note why, then export a decision card for local review.</p>
      </div>
      <div className="next__controls">
        <div className="next__col next__col--choose">
          <span className="next__label">
            <i>1</i>Strategy
          </span>
          <SelectControl
            label="Choose a strategy"
            value={locked ? '' : chosen}
            disabled={locked}
            title={locked ? lockText : undefined}
            onChange={setChosen}
            options={[
              { value: '', label: 'Choose a strategy' },
              ...strategies.map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
        </div>
        <div className="next__col next__col--reason">
          <label className="next__label" htmlFor="decision-reason">
            <i>2</i>Why does this fit your farm?
          </label>
          <textarea
            id="decision-reason"
            placeholder="Record your reason and questions for local review"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="next__col next__col--export">
          <span className="next__label">
            <i>3</i>Export
          </span>
          <button
            type="button"
            className="btn next__export"
            disabled={!canExport}
            title={onExport ? undefined : 'Decision cards need a live run (DEMO data cannot be exported)'}
            onClick={doExport}
          >
            <Icon src={downloadIcon} size={16} />
            {exp.status === 'saving' ? 'Exporting…' : 'Export decision card'}
          </button>
          {locked && (
            <p className="next__helper">
              <Icon src={lockIcon} size={14} />
              {lockText}
            </p>
          )}
        </div>
      </div>
      {exp.status === 'failed' && (
        <p className="run-error" role="alert">
          ⚠ The decision card was not saved: {exp.message}
        </p>
      )}
      {exp.status === 'done' && (
        <div className="card-result" role="status">
          <strong>
            Decision card saved{exp.card.is_demo ? ' (DEMO)' : ''}: {strategies.find((s) => s.id === exp.card.chosen_strategy_id)?.name}
          </strong>
          <span>
            Run {exp.card.run.id} · model {exp.card.run.model_version} · {exp.card.sources.length} sources ·{' '}
            {exp.card.local_review_questions.length} questions for local review
          </span>
          <span className="row">
            <a href={apiUrl(exp.card.pdf_url ?? '')} target="_blank" rel="noreferrer">
              Download PDF
            </a>
            <a href={apiUrl(exp.card.json_url)} target="_blank" rel="noreferrer">
              Download JSON
            </a>
          </span>
        </div>
      )}
    </section>
  )
}

import { useState } from 'react'
import downloadIcon from '../../assets/v2/icon-download.svg'
import lockIcon from '../../assets/v2/icon-lock.svg'
import { Icon, SelectControl } from '../../components/ui'
import type { StrategyView } from '../../demo/figmaDemo'

const RERUN = 'Rerun comparison before choosing and exporting.'

/**
 * "Choose your next step" (Figma node 28:467). Choosing and exporting stay disabled while the
 * results are outdated, so a decision card can never be built on stale numbers.
 */
export function NextStep({ strategies, outdated }: { strategies: readonly StrategyView[]; outdated: boolean }) {
  const [chosen, setChosen] = useState('')
  const [reason, setReason] = useState('')
  const canExport = !outdated && chosen !== '' && reason.trim() !== ''

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
            value={outdated ? '' : chosen}
            disabled={outdated}
            title={outdated ? RERUN : undefined}
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
          <button type="button" className="btn next__export" disabled={!canExport}>
            <Icon src={downloadIcon} size={16} />
            Export decision card
          </button>
          {outdated && (
            <p className="next__helper">
              <Icon src={lockIcon} size={14} />
              {RERUN}
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

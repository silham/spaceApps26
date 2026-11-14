import { useState } from 'react'
import { SelectControl } from '../../components/Control'
import { ctl } from '../../components/ctl'
import type { StrategyView } from '../../demo/figmaDemo'

const RERUN = 'Rerun comparison before choosing and exporting.'

/**
 * "Choose your next step" (Figma node 3:327). Choosing and exporting stay disabled while the
 * results are outdated, so a decision card can never be built on stale numbers.
 */
export function NextStep({ strategies, outdated }: { strategies: readonly StrategyView[]; outdated: boolean }) {
  const [chosen, setChosen] = useState('')
  const [reason, setReason] = useState('')
  const canExport = !outdated && chosen !== '' && reason.trim() !== ''

  return (
    <section className="card next" aria-labelledby="next-h">
      <h2 id="next-h">Choose your next step</h2>
      <div className="next__controls">
        <SelectControl
          label="Choose a strategy"
          variant="neutral"
          className="next__choose"
          value={outdated ? '' : chosen}
          disabled={outdated}
          title={outdated ? RERUN : undefined}
          onChange={setChosen}
          options={[
            { value: '', label: 'Choose a strategy' },
            ...strategies.map((s) => ({ value: s.id, label: s.name })),
          ]}
        />
        <div className="next__reason">
          <label htmlFor="decision-reason">Why does this fit your farm?</label>
          <textarea
            id="decision-reason"
            placeholder="Record your reason and questions for local review"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="next__export">
          <button type="button" className={ctl('neutral')} disabled={!canExport}>
            ▣  Export decision card
          </button>
          {outdated && <p>{RERUN}</p>}
        </div>
      </div>
    </section>
  )
}

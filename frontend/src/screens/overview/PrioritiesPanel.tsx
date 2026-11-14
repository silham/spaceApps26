import type { CSSProperties } from 'react'
import leafIcon from '../../assets/icon-leaf-22.svg'
import waterIcon from '../../assets/icon-water-22.svg'
import { SelectControl } from '../../components/Control'
import { ctl } from '../../components/ctl'

export interface Priorities {
  conserveWater: number
  protectSoil: number
}

// The supported-edit set is still open (docs/decisions.md D6), so each constraint offers only its
// current value. Add options here once D6 is resolved; don't invent them.
const PENDING = 'More options once supported edits are decided (D6)'
const single = (value: string) => [{ value, label: value }]

function PrioritySlider({
  id,
  label,
  icon,
  tone,
  value,
  onChange,
}: {
  id: string
  label: string
  icon: string
  tone: 'water' | 'soil'
  value: number
  onChange: (value: number) => void
}) {
  return (
    <div className="priority">
      <img src={icon} width={22} height={22} alt="" />
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        value={value}
        className={`slider slider--${tone}`}
        style={{ '--pct': `${value}%` } as CSSProperties}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  )
}

/** "What matters to your farm?" (Figma node 3:124): priorities kept separate from hard constraints. */
export function PrioritiesPanel({
  priorities,
  onPriorities,
  constraints,
  irrigationChanged,
  marketCrop,
  onMarketCrop,
}: {
  priorities: Priorities
  onPriorities: (priorities: Priorities) => void
  constraints: { irrigationLimit: string; soilProfile: string; equipment: string }
  irrigationChanged: boolean
  marketCrop: boolean
  onMarketCrop: (value: boolean) => void
}) {
  return (
    <section className="card priorities" aria-labelledby="priorities-h">
      <h2 id="priorities-h">What matters to your farm?</h2>
      <PrioritySlider
        id="priority-water"
        label="Conserve water"
        icon={waterIcon}
        tone="water"
        value={priorities.conserveWater}
        onChange={(conserveWater) => onPriorities({ ...priorities, conserveWater })}
      />
      <PrioritySlider
        id="priority-soil"
        label="Protect soil"
        icon={leafIcon}
        tone="soil"
        value={priorities.protectSoil}
        onChange={(protectSoil) => onPriorities({ ...priorities, protectSoil })}
      />
      <div className="divider" />
      <h3>Farm constraints</h3>
      <div className="constraint">
        <span className="constraint__label">Irrigation limit</span>
        <SelectControl
          label="Irrigation limit"
          value={constraints.irrigationLimit}
          options={single(constraints.irrigationLimit)}
          title={PENDING}
        />
        {irrigationChanged && <span className={ctl('warning')}>Changed</span>}
      </div>
      <div className="constraint">
        <span className="constraint__label">Soil profile</span>
        <SelectControl
          label="Soil profile"
          value={constraints.soilProfile}
          options={single(constraints.soilProfile)}
          title={PENDING}
        />
      </div>
      <div className="constraint">
        <span className="constraint__label">Equipment</span>
        <SelectControl
          label="Equipment"
          value={constraints.equipment}
          options={single(constraints.equipment)}
          title={PENDING}
        />
      </div>
      <label className="checkbox">
        <input type="checkbox" checked={marketCrop} onChange={(e) => onMarketCrop(e.target.checked)} />
        Must include a market crop
      </label>
      <button type="button" className="link" aria-disabled="true" title="Farm details editor is not built yet">
        Edit farm details ↗
      </button>
    </section>
  )
}

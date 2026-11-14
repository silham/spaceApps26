import type { CSSProperties } from 'react'
import dropIcon from '../../assets/v2/icon-drop-16.svg'
import leafIcon from '../../assets/v2/icon-leaf-16.svg'
import { Badge, Icon, SelectControl } from '../../components/ui'
import type { SimulationMode } from '../../types/contracts'

export interface Priorities {
  conserveWater: number
  protectSoil: number
}

// The supported-edit set is still open (docs/decisions.md D6), so each constraint offers only its
// current value. Add options here once D6 is resolved; don't invent them.
const PENDING = 'More options once supported edits are decided (D6)'
const single = (value: string) => [{ value, label: value }]

export function PrioritySlider({
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
      <label htmlFor={id}>
        <span className={`tile ${tone === 'water' ? 'tile--info' : 'tile--success'}`}>
          <Icon src={icon} size={16} />
        </span>
        {label}
      </label>
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

/** "What matters to your farm?" (Figma node 26:197): priorities kept separate from hard constraints. */
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
      <div className="card-title card-title--small">
        <h2 id="priorities-h">What matters to your farm?</h2>
        <p>Drag to weight what the comparison should favour.</p>
      </div>
      <PrioritySlider
        id="priority-water"
        label="Conserve water"
        icon={dropIcon}
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
        <span className="constraint__label">
          Irrigation limit
          {irrigationChanged && <Badge tone="warning">Changed</Badge>}
        </span>
        <SelectControl
          label="Irrigation limit"
          className={irrigationChanged ? 'select--changed' : ''}
          value={constraints.irrigationLimit}
          options={single(constraints.irrigationLimit)}
          title={PENDING}
        />
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

/**
 * Live constraints for a loaded farm (D6): the irrigation mode and limit are editable; soil and
 * equipment come from the stored soil profile and the farmer's confirmation, edited in the farm form.
 * Priorities only order feasible options (D12); they never change a constraint.
 */
export function LivePrioritiesPanel({
  priorities,
  onPriorities,
  mode,
  onMode,
  allocationMm,
  onAllocation,
  allocationChanged,
  soilLabel,
  equipmentLabel,
  cropsLabel,
  onEditFarm,
}: {
  priorities: Priorities
  onPriorities: (priorities: Priorities) => void
  mode: SimulationMode
  onMode: (m: SimulationMode) => void
  allocationMm: number | null
  onAllocation: (mm: number | null) => void
  allocationChanged: boolean
  soilLabel: string
  equipmentLabel: string
  cropsLabel: string
  onEditFarm: () => void
}) {
  return (
    <section className="card priorities" aria-labelledby="priorities-h">
      <div className="card-title card-title--small">
        <h2 id="priorities-h">What matters to your farm?</h2>
        <p>Priorities order the feasible options. They never override a constraint.</p>
      </div>
      <PrioritySlider
        id="priority-water"
        label="Conserve water"
        icon={dropIcon}
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
        <span className="constraint__label">Irrigation</span>
        <SelectControl
          label="Irrigation mode"
          value={mode}
          onChange={(v) => onMode(v as SimulationMode)}
          options={[
            { value: 'irrigation_needed', label: 'As needed (refill rule)' },
            { value: 'fixed_allocation', label: 'Fixed limit per season' },
          ]}
        />
      </div>
      {mode === 'fixed_allocation' && (
        <div className="constraint">
          <span className="constraint__label">
            Irrigation limit
            {allocationChanged && <Badge tone="warning">Changed</Badge>}
          </span>
          <label className={`number-input ${allocationChanged ? 'number-input--changed' : ''}`}>
            <input
              type="number"
              min={0}
              step={10}
              aria-label="Irrigation limit in mm per irrigated season"
              value={allocationMm ?? ''}
              onChange={(e) => onAllocation(e.target.value === '' ? null : Number(e.target.value))}
            />
            mm / season
          </label>
        </div>
      )}
      <div className="constraint">
        <span className="constraint__label">Soil profile</span>
        <span className="small">{soilLabel}</span>
      </div>
      <div className="constraint">
        <span className="constraint__label">Equipment</span>
        <span className="small">{equipmentLabel}</span>
      </div>
      <div className="constraint">
        <span className="constraint__label">Crops available</span>
        <span className="small">{cropsLabel}</span>
      </div>
      <button type="button" className="link" onClick={onEditFarm}>
        Confirm farm details ↗
      </button>
    </section>
  )
}

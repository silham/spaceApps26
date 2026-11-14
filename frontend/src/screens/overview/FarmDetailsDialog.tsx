import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { CropProfile, FarmerContext } from '../../types/contracts'

/**
 * "Confirm farm details" (guide §4 Observe). No Figma frame: a native dialog with the dashboard's
 * control styles. Every field is optional; anything left blank stays unconfirmed (null), never guessed.
 */
export function FarmDetailsDialog({
  siteId,
  open,
  initial,
  crops,
  soilSummary,
  onClose,
  onSaved,
}: {
  siteId: string
  open: boolean
  initial: FarmerContext | null
  crops: CropProfile[]
  soilSummary: string
  onClose: () => void
  onSaved: (ctx: FarmerContext) => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [ctx, setCtx] = useState<FarmerContext>(initial ?? {})
  const [limitCrops, setLimitCrops] = useState(initial?.available_crop_ids != null)
  const [state, setState] = useState<{ saving: boolean; error?: string }>({ saving: false })

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) {
      setCtx(initial ?? {})
      setLimitCrops(initial?.available_crop_ids != null)
      setState({ saving: false })
      d.showModal()
    }
    if (!open && d.open) d.close()
  }, [open, initial])

  const set = <K extends keyof FarmerContext>(k: K, v: FarmerContext[K]) => setCtx((c) => ({ ...c, [k]: v }))
  const available = new Set(ctx.available_crop_ids ?? crops.map((c) => c.id))
  const text = (v: string) => (v.trim() === '' ? null : v)

  const save = () => {
    setState({ saving: true })
    const body: FarmerContext = {
      ...ctx,
      value_kind: 'farmer_input',
      available_crop_ids: limitCrops ? [...available] : null,
      equipment: (ctx.equipment ?? []).filter((e) => e.trim() !== ''),
    }
    api.saveFarmerContext(siteId, body).then(
      (saved) => {
        setState({ saving: false })
        onSaved(saved)
      },
      (e: Error) => setState({ saving: false, error: e.message }),
    )
  }

  return (
    <dialog ref={ref} className="farm-dialog" aria-labelledby="farm-dialog-h" onClose={onClose}>
      <form
        className="form"
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault()
          save()
        }}
      >
        <div className="card-title">
          <h2 id="farm-dialog-h">Confirm farm details</h2>
          <p>
            What you enter is stored as a farmer input and shown on the decision card. Leave anything you are unsure about blank.
          </p>
        </div>
        <label>
          Planting history
          <input
            type="text"
            placeholder="e.g. corn planted late April most years"
            value={ctx.planting_history ?? ''}
            onChange={(e) => set('planting_history', text(e.target.value))}
          />
        </label>
        <label>
          Harvest history
          <input type="text" value={ctx.harvest_history ?? ''} onChange={(e) => set('harvest_history', text(e.target.value))} />
        </label>
        <fieldset>
          <legend>Soil</legend>
          <span className="small muted">Stored profile: {soilSummary}</span>
          <label className="check">
            <input
              type="checkbox"
              checked={ctx.soil_confirmed === true}
              onChange={(e) => set('soil_confirmed', e.target.checked ? true : null)}
            />
            This matches my field
          </label>
          <input
            type="text"
            aria-label="Soil notes"
            placeholder="Notes (e.g. sandier on the north side)"
            value={ctx.soil_notes ?? ''}
            onChange={(e) => set('soil_notes', text(e.target.value))}
          />
        </fieldset>
        <label>
          Irrigation allocation (mm per irrigated season)
          <input
            type="number"
            min={0}
            value={ctx.irrigation_allocation_mm ?? ''}
            onChange={(e) => set('irrigation_allocation_mm', e.target.value === '' ? null : Number(e.target.value))}
          />
          <span className="small muted">Used as the default limit when you choose fixed-allocation mode.</span>
        </label>
        <label>
          Equipment (comma separated)
          <input
            type="text"
            value={(ctx.equipment ?? []).join(', ')}
            onChange={(e) => set('equipment', e.target.value.split(',').map((x) => x.trim()))}
          />
        </label>
        <fieldset>
          <legend>Crops you can grow</legend>
          <label className="check">
            <input type="checkbox" checked={limitCrops} onChange={(e) => setLimitCrops(e.target.checked)} />
            Only some crops are possible on this farm
          </label>
          {limitCrops &&
            crops.map((c) => (
              <label key={c.id} className="check">
                <input
                  type="checkbox"
                  checked={available.has(c.id)}
                  onChange={(e) => {
                    const next = new Set(available)
                    if (e.target.checked) next.add(c.id)
                    else next.delete(c.id)
                    set('available_crop_ids', [...next])
                  }}
                />
                {c.name}
              </label>
            ))}
          <span className="small muted">A strategy using an unavailable crop becomes infeasible, with that reason.</span>
        </fieldset>
        <label>
          Market or use
          <input type="text" value={ctx.market_use ?? ''} onChange={(e) => set('market_use', text(e.target.value))} />
        </label>
        <label className="check">
          <input type="checkbox" checked={ctx.confirmed === true} onChange={(e) => set('confirmed', e.target.checked)} />
          I confirm these details
        </label>
        {state.error && (
          <p className="run-error" role="alert">
            ⚠ Not saved: {state.error}
          </p>
        )}
        <div className="form__actions">
          <button type="button" className="btn btn--secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn--primary" disabled={state.saving}>
            {state.saving ? 'Saving…' : 'Save farm details'}
          </button>
        </div>
      </form>
    </dialog>
  )
}

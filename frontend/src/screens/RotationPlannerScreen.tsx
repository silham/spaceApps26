import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { StateView } from '../components/StateView'
import { Badge, SelectControl } from '../components/ui'
import {
  MAX_ROTATIONS,
  MAX_SEASONS,
  ROTATION_END,
  ROTATION_START,
  blankSeason,
  draftsFromStrategies,
  harvestDate,
  rotationsProblem,
  rotationsRequest,
  seasonDays,
  type RotationDraft,
  type SeasonDraft,
} from '../live/model'
import type { CropProfile, Strategy } from '../types/contracts'

const newRotation = (n: number): RotationDraft => ({
  name: n === 1 ? 'Current practice' : `Alternative ${n - 1}`,
  seasons: [blankSeason()],
})

/**
 * Rotation builder (D15): the farmer picks crops and planting dates for up to three rotations of this farm; the
 * first is current practice. Saving stores them; "Save and compare" then runs them on the farm's own weather and
 * soil. No Figma frame: card, button, badge and form patterns of frame 25:49.
 */
export function RotationPlannerScreen({
  siteId,
  onCompared,
}: {
  siteId: string
  /** The comparison finished (or its failure should be seen on the overview). */
  onCompared: () => void
}) {
  const crops = useAsync(api.rotationCrops, [])
  const saved = useAsync(() => api.strategies(siteId), [siteId])
  const [rotations, setRotations] = useState<RotationDraft[] | null>(null)
  const [busy, setBusy] = useState<'idle' | 'saving' | 'running'>('idle')
  const [error, setError] = useState('')
  const [savedNote, setSavedNote] = useState('')
  const [strategies, setStrategies] = useState<Strategy[]>([])

  const cropMap = useMemo(
    () => new Map<string, CropProfile>((crops.status === 'ready' ? crops.data : []).map((c) => [c.id, c])),
    [crops],
  )

  // Open with what is already stored; a farm without rotations starts with one empty "Current practice".
  useEffect(() => {
    if (saved.status !== 'ready' || rotations !== null) return
    setStrategies(saved.data)
    setRotations(saved.data.length ? draftsFromStrategies(saved.data) : [newRotation(1)])
  }, [saved, rotations])

  if (crops.status === 'loading' || saved.status === 'loading' || rotations === null) {
    if (saved.status === 'error' || crops.status === 'error')
      return (
        <>
          <h1 className="page-title" tabIndex={-1}>Rotation planner</h1>
          <StateView kind="failed" title="Could not load the planner">
            {(saved.status === 'error' ? saved.error : crops.status === 'error' ? crops.error : new Error('')).message}
          </StateView>
        </>
      )
    return (
      <>
        <h1 className="page-title" tabIndex={-1}>Rotation planner</h1>
        <StateView kind="loading" title="Loading the planner…" />
      </>
    )
  }

  const problem = rotationsProblem(rotations, cropMap)
  const cropOptions = [
    { value: '', label: 'Choose a crop' },
    ...[...cropMap.values()].map((c) => ({ value: c.id, label: c.name })),
  ]
  const edit = (i: number, change: (r: RotationDraft) => RotationDraft) => {
    setRotations(rotations.map((r, k) => (k === i ? change(r) : r)))
    setStrategies([])
    setSavedNote('')
  }
  const editSeason = (i: number, j: number, patch: Partial<SeasonDraft>) =>
    edit(i, (r) => ({ ...r, seasons: r.seasons.map((s, k) => (k === j ? { ...s, ...patch } : s)) }))

  async function saveAndCompare() {
    if (problem || !rotations) return
    setBusy('saving')
    setError('')
    try {
      const stored = await api.saveRotations(siteId, rotationsRequest(rotations))
      setStrategies(stored)
      setSavedNote('Rotations saved.')
      setBusy('running')
      await api.createRun({ site_id: siteId })
      onCompared()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save or run the rotations.')
      setBusy('idle')
    }
  }

  return (
    <>
      <div className="page-head">
        <h1 className="page-title" tabIndex={-1}>
          Rotation planner
        </h1>
        <p className="muted">
          Choose the crops you would grow, up to {MAX_ROTATIONS} rotations. The first is your current practice; the others
          are compared with it on the same historical weather, soil and water.
        </p>
      </div>

      <StateView kind="unavailable" title="How to read the results">
        Crop values are generic FAO table values, not calibrated to your field. Harvest is the share of the water-unlimited
        yield, lost to water stress only (not nutrients, pests, heat or variety). Tonnes per hectare appear only where you
        enter your own usual yield. Weather is resampled from history: it is not a forecast. The comparison covers{' '}
        {ROTATION_START.slice(0, 4)}–{ROTATION_END.slice(0, 4)} as a model calendar.
      </StateView>

      <div className="rot-grid">
        {rotations.map((rotation, i) => {
          const stored = strategies[i] // cleared on any edit, so it always belongs to what is shown
          return (
            <section key={i} className="card page-card rot-card" aria-label={`Rotation ${i + 1}`}>
              <div className="rot-card__head">
                <label className="rot-card__name">
                  <span className="small muted">{i === 0 ? 'Current practice' : `Alternative ${i}`}</span>
                  <input
                    type="text"
                    value={rotation.name}
                    maxLength={120}
                    aria-label={`Rotation ${i + 1} name`}
                    onChange={(e) => edit(i, (r) => ({ ...r, name: e.target.value }))}
                  />
                </label>
                {i === 0 && <Badge tone="neutral" dot={false}>Baseline</Badge>}
                {rotations.length > 1 && (
                  <button
                    type="button"
                    className="btn btn--secondary"
                    onClick={() => {
                      setRotations(rotations.filter((_, k) => k !== i))
                      setStrategies([])
                      setSavedNote('')
                    }}
                  >
                    Remove
                  </button>
                )}
              </div>

              <ol className="rot-seasons">
                {rotation.seasons.map((season, j) => {
                  const crop = cropMap.get(season.crop_id)
                  const harvest = harvestDate(season.plant_date, crop)
                  const days = seasonDays(crop)
                  return (
                    <li key={j} className="rot-season">
                      <div className="rot-season__row">
                        <strong>Season {j + 1}</strong>
                        {rotation.seasons.length > 1 && (
                          <button
                            type="button"
                            className="link"
                            onClick={() => edit(i, (r) => ({ ...r, seasons: r.seasons.filter((_, k) => k !== j) }))}
                          >
                            Remove season
                          </button>
                        )}
                      </div>
                      <div className="rot-season__fields">
                        <SelectControl
                          label={`Rotation ${i + 1} season ${j + 1} crop`}
                          value={season.crop_id}
                          options={cropOptions}
                          onChange={(v) => editSeason(i, j, { crop_id: v })}
                        />
                        <label className="rot-field">
                          <span className="small muted">Planting date</span>
                          <input
                            type="date"
                            value={season.plant_date}
                            min={ROTATION_START}
                            max={ROTATION_END}
                            onChange={(e) => editSeason(i, j, { plant_date: e.target.value })}
                          />
                        </label>
                        <div className="segmented" role="radiogroup" aria-label={`Rotation ${i + 1} season ${j + 1} water`}>
                          <button
                            type="button"
                            role="radio"
                            aria-checked={!season.irrigated}
                            onClick={() => editSeason(i, j, { irrigated: false })}
                          >
                            Rainfed
                          </button>
                          <button
                            type="button"
                            role="radio"
                            aria-checked={season.irrigated}
                            onClick={() => editSeason(i, j, { irrigated: true })}
                          >
                            Irrigated
                          </button>
                        </div>
                        <label className="rot-field">
                          <span className="small muted">Your usual yield (t/ha), optional</span>
                          <input
                            type="number"
                            min="0"
                            max="30"
                            step="0.1"
                            inputMode="decimal"
                            value={season.usual_yield}
                            placeholder="e.g. 8"
                            onChange={(e) => editSeason(i, j, { usual_yield: e.target.value })}
                          />
                        </label>
                      </div>
                      {crop && (
                        <p className="small muted">
                          {harvest
                            ? `Harvest about ${harvest} (${days} days after planting).`
                            : season.plant_date
                              ? 'Harvest date unavailable for this crop.'
                              : `Takes about ${days} days from planting to harvest.`}
                        </p>
                      )}
                    </li>
                  )
                })}
              </ol>

              {rotation.seasons.length < MAX_SEASONS && (
                <button
                  type="button"
                  className="btn btn--secondary rot-card__add"
                  onClick={() => edit(i, (r) => ({ ...r, seasons: [...r.seasons, blankSeason()] }))}
                >
                  + Add a season
                </button>
              )}

              {stored?.feasibility && !stored.feasibility.feasible && (
                <p role="note" className="alert">
                  ⚠ Not feasible: {stored.feasibility.reasons?.join('; ') || 'no reason recorded'}
                </p>
              )}
            </section>
          )
        })}
      </div>

      <div className="rot-actions">
        {rotations.length < MAX_ROTATIONS && (
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => {
              setRotations([...rotations, newRotation(rotations.length + 1)])
              setStrategies([])
              setSavedNote('')
            }}
          >
            + Add a rotation to compare
          </button>
        )}
        <span className="spacer" />
        <button
          type="button"
          className="btn btn--primary"
          disabled={Boolean(problem) || busy !== 'idle'}
          title={problem ?? undefined}
          onClick={() => void saveAndCompare()}
        >
          {busy === 'saving' ? 'Saving…' : busy === 'running' ? 'Running the comparison…' : 'Save and compare'}
        </button>
      </div>
      {problem && busy === 'idle' && <p className="small muted">{problem}</p>}
      {busy === 'running' && (
        <StateView kind="loading" title="Running the comparison…">
          Every rotation is simulated on the same resampled weather paths. This takes a few seconds.
        </StateView>
      )}
      {savedNote && busy === 'idle' && !error && (
        <p className="account__ok" role="status">
          {savedNote}
        </p>
      )}
      {error && (
        <div className="state state--failed" role="alert">
          <strong>Could not finish</strong>
          {error}
          {savedNote && (
            <button type="button" className="link" onClick={onCompared}>
              Open the overview anyway
            </button>
          )}
        </div>
      )}
    </>
  )
}

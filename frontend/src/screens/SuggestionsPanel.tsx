import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { StateView } from '../components/StateView'
import { Badge, SelectControl } from '../components/ui'
import type {
  CandidateMetric,
  CropProfile,
  RecommendationJob,
  RecommendationRequest,
  RotationCandidate,
  SoilRuleResult,
} from '../types/contracts'

type Objective = 'cover' | 'irrigation' | 'soil_health'
const OBJECTIVE_LABEL: Record<Objective, string> = {
  cover: 'Keep the soil covered',
  irrigation: 'Use less irrigation',
  soil_health: 'Soil health (crop families, legumes)',
}
const ORDERS: [Objective, Objective, Objective][] = [
  ['cover', 'irrigation', 'soil_health'],
  ['cover', 'soil_health', 'irrigation'],
  ['irrigation', 'cover', 'soil_health'],
  ['irrigation', 'soil_health', 'cover'],
  ['soil_health', 'cover', 'irrigation'],
  ['soil_health', 'irrigation', 'cover'],
]

const metric = (c: RotationCandidate, name: string) => c.metrics.find((m) => m.metric === name && m.season_index == null)
const range = (m: CandidateMetric | undefined, unit: string) =>
  !m || m.p50 == null ? '—' : `${Math.round(m.p50)} ${unit}${m.p10 != null && m.p90 != null ? ` (${Math.round(m.p10)}–${Math.round(m.p90)})` : ''}`
const delta = (m: CandidateMetric | undefined, unit: string) =>
  m?.delta_p50_vs_current == null ? null : `${m.delta_p50_vs_current > 0 ? '+' : ''}${Math.round(m.delta_p50_vs_current)} ${unit} vs current`

export function SoilRules({ rules }: { rules: SoilRuleResult[] }) {
  if (!rules.length) return null
  return (
    <ul className="soil-rules">
      {rules.map((r) => (
        <li key={r.rule_id} className={`soil-rules__${r.status}`}>
          <span aria-hidden="true">{r.status === 'met' ? '✓' : r.status === 'not_met' ? '⚠' : '?'}</span>{' '}
          <strong>{r.label}</strong>
          <span className="sr-only">: {r.status === 'met' ? 'met' : r.status === 'not_met' ? 'not met' : 'unknown'}</span>
          <span className="small muted"> {r.explanation}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * Suggested rotations (D16): the farmer orders three priorities and states constraints; the API searches rotations
 * that suit the predicted weather and returns the best trade-offs. No Figma frame: card, badge and form patterns.
 */
export function SuggestionsPanel({
  siteId,
  crops,
  onUse,
}: {
  siteId: string
  crops: CropProfile[]
  onUse: (c: RotationCandidate) => void
}) {
  const [order, setOrder] = useState(0)
  const [irrigation, setIrrigation] = useState(true)
  const [floor, setFloor] = useState('60')
  const [seasons, setSeasons] = useState('3')
  const [require, setRequire] = useState('')
  const [job, setJob] = useState<RecommendationJob | null>(null)
  const [error, setError] = useState('')
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const running = job?.status === 'queued' || job?.status === 'running'
  const poll = (id: string) => {
    timer.current = window.setTimeout(() => {
      api.suggestions(siteId, id).then(
        (j) => {
          setJob(j)
          if (j.status === 'queued' || j.status === 'running') poll(id)
        },
        (e: Error) => setError(e.message),
      )
    }, 2000)
  }
  const find = () => {
    const y = Number(floor)
    if (!(y >= 0 && y <= 100)) {
      setError('The yield floor must be between 0 and 100%.')
      return
    }
    setError('')
    const req: RecommendationRequest = {
      priorities: ORDERS[order]!,
      irrigation_allowed: irrigation,
      max_seasons: Number(seasons),
      min_relative_yield_pct: y,
      require_crop_id: require || null,
      exclude_crop_ids: [],
    }
    api.startSuggestions(siteId, req).then(
      (j) => {
        setJob(j)
        poll(j.id)
      },
      (e: Error) => setError(e.message),
    )
  }

  const cropName = (id: string | null | undefined) => crops.find((c) => c.id === id)?.name ?? id ?? 'fallow'
  const card = (c: RotationCandidate, current = false) => (
    <article key={c.name + (c.rank ?? 'cur')} className="card suggestion" aria-label={current ? 'Current practice' : `Option ${c.rank}`}>
      <div className="suggestion__head">
        {current ? <Badge tone="neutral" dot={false}>Current practice</Badge> : <Badge tone="success" dot={false}>Option {c.rank}</Badge>}
        <h3>{c.name}</h3>
      </div>
      <ol className="suggestion__seasons">
        {c.seasons.map((s) => (
          <li key={s.plant_date}>
            {cropName(s.crop_id)} · {s.plant_date} to {s.end_date} · {s.irrigation_rule ? 'irrigated' : 'rainfed'}
          </li>
        ))}
      </ol>
      <dl className="suggestion__metrics">
        <div>
          <dt>Possible low-cover days</dt>
          <dd>
            {range(metric(c, 'possible_low_cover_days'), 'days')}
            {delta(metric(c, 'possible_low_cover_days'), 'days') && <span className="small muted"> · {delta(metric(c, 'possible_low_cover_days'), 'days')}</span>}
          </dd>
        </div>
        <div>
          <dt>Irrigation (net)</dt>
          <dd>
            {range(metric(c, 'irrigation_mm'), 'mm')}
            {delta(metric(c, 'irrigation_mm'), 'mm') && <span className="small muted"> · {delta(metric(c, 'irrigation_mm'), 'mm')}</span>}
          </dd>
        </div>
        <div>
          <dt>Relative yield by season (water-limited)</dt>
          <dd>
            {c.metrics
              .filter((m) => m.metric === 'relative_yield_pct')
              .map((m) => `${cropName(c.seasons[m.season_index ?? 0]?.crop_id)} ${m.p50 == null ? '—' : `${Math.round(m.p50)}%`}`)
              .join(' · ') || 'not available'}
          </dd>
        </div>
      </dl>
      <SoilRules rules={c.soil_health} />
      {(c.why.length > 0 || c.trade_offs.length > 0) && (
        <ul className="small suggestion__why">
          {[...c.why, ...c.trade_offs].map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
      {!current && (
        <button type="button" className="btn btn--secondary" onClick={() => onUse(c)}>
          Use this rotation
        </button>
      )}
    </article>
  )

  return (
    <section className="card page-card suggestions" aria-labelledby="suggest-h">
      <div className="card-title card-title--small">
        <h2 id="suggest-h">Suggest rotations for me</h2>
        <p>
          Searches rotations of the catalog crops that suit the predicted temperatures, simulates them on the same weather
          paths, and orders the best trade-offs by what matters most to you. You can then compare any of them below.
        </p>
      </div>
      <div className="suggestions__form">
        <div className="rot-field">
          <span className="small muted" aria-hidden="true">What matters most, in order</span>
          <SelectControl
          label="What matters most, in order"
          value={String(order)}
          options={ORDERS.map((o, i) => ({ value: String(i), label: o.map((x) => OBJECTIVE_LABEL[x]).join(' › ') }))}
          onChange={(v) => setOrder(Number(v))}
        />
        </div>
        <label className="rot-field">
          <span className="small muted">Lowest acceptable relative yield (%)</span>
          <input type="number" min={0} max={100} step={5} value={floor} onChange={(e) => setFloor(e.target.value)} />
        </label>
        <div className="rot-field">
          <span className="small muted" aria-hidden="true">Seasons at most</span>
          <SelectControl
          label="Seasons at most"
          value={seasons}
          options={['1', '2', '3'].map((v) => ({ value: v, label: v }))}
          onChange={setSeasons}
        />
        </div>
        <div className="rot-field">
          <span className="small muted" aria-hidden="true">Must include</span>
          <SelectControl
          label="Must include"
          value={require}
          options={[{ value: '', label: 'Any crop' }, ...crops.map((c) => ({ value: c.id, label: c.name }))]}
          onChange={setRequire}
        />
        </div>
        <label className="check-inline">
          <input type="checkbox" checked={irrigation} onChange={(e) => setIrrigation(e.target.checked)} />
          Irrigation is possible
        </label>
        <button type="button" className="btn btn--primary" disabled={running} onClick={find}>
          {running ? 'Searching…' : 'Find rotations'}
        </button>
      </div>
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}
      {running && job && (
        <div role="status" className="suggestions__progress">
          <progress max={1} value={job.progress} aria-label="Search progress" /> <span className="small muted">{job.message}</span>
        </div>
      )}
      {job?.status === 'failed' && (
        <StateView kind="failed" title="The search could not finish">
          {job.message}
        </StateView>
      )}
      {job?.status === 'done' && (
        <>
          <p className="small muted">
            {job.candidates_considered} rotations considered from {job.horizon_start} to {job.horizon_end}; shown with the{' '}
            {job.range_label} over {job.n_paths} weather paths.
            {job.message ? ` ${job.message}` : ''}
          </p>
          <div className="suggestions__grid">
            {(job.candidates ?? []).map((c) => card(c))}
            {job.current_practice && card(job.current_practice, true)}
          </div>
          <details className="small">
            <summary>How these are found</summary>
            <ul>
              {[...(job.assumptions ?? []), ...(job.limitations ?? [])].map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            <p>Sources: {(job.source_ids ?? []).join(', ')}</p>
          </details>
        </>
      )}
    </section>
  )
}

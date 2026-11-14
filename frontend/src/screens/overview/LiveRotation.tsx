import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { api } from '../../api/client'
import cloudIcon from '../../assets/v2/icon-cloud.svg'
import playIcon from '../../assets/v2/icon-play-dark.svg'
import chevron12 from '../../assets/v2/chevron-light-12.svg'
import chevron14 from '../../assets/v2/chevron-light-14.svg'
import { StateView } from '../../components/StateView'
import { Badge, Icon } from '../../components/ui'
import { MAX_SHIFT_DAYS, TONES, driestWindow, isFeasible, yearsLabel } from '../../live/model'
import type { CropProfile, ReplayTrace, RunDetail, Strategy } from '../../types/contracts'

const DAY_MS = 86_400_000
const TICK_MS = 60
const SPEEDS = [1, 2, 4]
const fullDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const monthYear = new Intl.DateTimeFormat('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' })
const ms = (iso: string) => Date.parse(`${iso}T00:00:00Z`)

function horizonOf(run: RunDetail): [number, number] {
  const h = run.run.input_versions?.horizon ?? ''
  const m = h.match(/(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})/)
  if (m?.[1] && m[2]) return [ms(m[1]), ms(m[2]) + DAY_MS]
  const ds = run.strategies.flatMap((s) => s.seasons.flatMap((x) => [ms(x.plant_date), ms(x.end_date)]))
  return [Math.min(...ds), Math.max(...ds) + DAY_MS]
}

const shortCrop = (crops: Map<string, CropProfile>, id: string | null | undefined) => {
  if (!id) return 'Fallow'
  const name = crops.get(id)?.name ?? id
  return name.replace(/\s*\(.*\)$/, '').replace(/, field$/, '')
}

/**
 * Live rotation rows for the shown run: seasons placed by date across the comparison horizon, a ±14-day
 * planting stepper per strategy (D6), and the shared weather replay. One replay trace drives every row,
 * so all strategies are read against the same historical day. No Figma frame: extends node 27:175.
 */
export function LiveRotation({
  run,
  outdated,
  crops,
  shifts,
  onShift,
  showRanges,
  onShowRanges,
  onExplore,
}: {
  run: RunDetail
  outdated: boolean
  crops: Map<string, CropProfile>
  shifts: Record<string, number>
  onShift: (strategyId: string, days: number) => void
  showRanges: boolean
  onShowRanges: (v: boolean) => void
  onExplore: () => void
}) {
  const [start, end] = horizonOf(run)
  const span = end - start
  const pct = (t: number) => `${Math.max(0, Math.min(100, ((t - start) / span) * 100))}%`
  const windows = run.replay_windows
  const firstPool = windows.find((w) => w.enabled && w.in_sample_pool) ?? windows.find((w) => w.enabled)
  const [years, setYears] = useState<number[] | null>(firstPool?.years ?? null)
  const [trace, setTrace] = useState<{ status: 'idle' | 'loading' | 'ready' | 'failed'; data?: ReplayTrace; error?: string }>({
    status: 'idle',
  })
  const [day, setDay] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [pausedAtTurn, setPausedAtTurn] = useState(false)

  useEffect(() => {
    setYears(firstPool?.years ?? null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.run.id])

  useEffect(() => {
    if (!years) return
    let cancelled = false
    setTrace({ status: 'loading' })
    setPlaying(false)
    setPausedAtTurn(false)
    setDay(0)
    api.replay(run.run.id, years).then(
      (data) => !cancelled && setTrace({ status: 'ready', data }),
      (e: Error) => !cancelled && setTrace({ status: 'failed', error: e.message }),
    )
    return () => {
      cancelled = true
    }
  }, [run.run.id, years])

  const data = trace.status === 'ready' ? trace.data : undefined
  const lastDay = data ? data.dates.length - 1 : 0
  const turnIdx = useMemo(() => (data?.turning_point ? data.dates.indexOf(data.turning_point) : -1), [data])

  useEffect(() => {
    if (!playing) return
    const t = window.setInterval(() => setDay((d) => Math.min(d + 1, lastDay)), TICK_MS / speed)
    return () => window.clearInterval(t)
  }, [playing, speed, lastDay])

  useEffect(() => {
    if (playing && turnIdx >= 0 && day === turnIdx && !pausedAtTurn) {
      setPlaying(false)
      setPausedAtTurn(true)
    }
    if (day >= lastDay) setPlaying(false)
  }, [day, playing, turnIdx, pausedAtTurn, lastDay])

  const window_ = windows.find((w) => years && w.years.join() === years.join())
  const dry = driestWindow(run)
  const dateIso = data?.dates[day]
  const sourceIso = data?.source_dates[day]
  const series = new Map(data?.series.map((s) => [s.strategy_id, s]) ?? [])
  const ticks: number[] = []
  for (let y = new Date(start).getUTCFullYear(); ms(`${y}-01-01`) < end; y++)
    for (const m of [1, 4, 7, 10]) {
      const t = ms(`${y}-${String(m).padStart(2, '0')}-01`)
      if (t >= start && t < end) ticks.push(t)
    }

  const row = (s: Strategy, i: number) => {
    const tone = TONES[i] ?? 'baseline'
    const shift = shifts[s.id] ?? 0
    const shiftedBefore = run.request.planting_shift_days?.[s.id] ?? 0
    const ser = series.get(s.id)
    const feasible = isFeasible(s)
    return (
      <div key={s.id} className={`ltl__row ${feasible ? '' : 'ltl__row--infeasible'}`}>
        <div className="ltl__name">
          {s.name.split(':')[0]}
          <small>{s.name.split(':').slice(1).join(':').trim() || (s.is_baseline ? 'current practice' : '')}</small>
          <span className={`stepper ${shift !== shiftedBefore ? 'stepper--changed' : ''}`}>
            Planting
            <button
              type="button"
              aria-label={`Plant ${s.name.split(':')[0]} one day earlier`}
              disabled={shift <= -MAX_SHIFT_DAYS}
              onClick={() => onShift(s.id, shift - 1)}
            >
              −
            </button>
            <output aria-live="polite">{shift === 0 ? 'as planned' : `${shift > 0 ? '+' : ''}${shift} d`}</output>
            <button
              type="button"
              aria-label={`Plant ${s.name.split(':')[0]} one day later`}
              disabled={shift >= MAX_SHIFT_DAYS}
              onClick={() => onShift(s.id, shift + 1)}
            >
              +
            </button>
          </span>
        </div>
        <div className="ltl__track" aria-label={`${s.name} seasons`}>
          {s.seasons.map((x) => (
            <span
              key={`${x.crop_id}-${x.plant_date}`}
              className={`ltl__seg ltl__seg--${tone} ${x.irrigation_rule ? '' : 'ltl__seg--rainfed'}`}
              style={{ left: pct(ms(x.plant_date)), width: `calc(${pct(ms(x.end_date) + DAY_MS)} - ${pct(ms(x.plant_date))})` }}
              title={`${crops.get(x.crop_id ?? '')?.name ?? 'Fallow'}: ${x.plant_date} → ${x.end_date} · ${
                x.irrigation_rule ? 'irrigated' : 'rainfed'
              }`}
            >
              {shortCrop(crops, x.crop_id)} · {x.irrigation_rule ? 'irrigated' : 'rainfed'}
            </span>
          ))}
        </div>
        <div className="ltl__readout">
          {!feasible ? (
            <span className="ltl__infeasible">Infeasible: {s.feasibility?.reasons?.join('; ')}</span>
          ) : ser && dateIso ? (
            <>
              Soil water <b>{ser.storage_mm[day] == null ? '—' : `${Math.round(ser.storage_mm[day] as number)} mm`}</b>
              <br />
              {ser.in_crop[day] ? (
                (ser.ks[day] ?? 1) < 1 ? (
                  <b>Crop water-stressed</b>
                ) : (
                  'Crop not stressed'
                )
              ) : (
                'No crop in the field'
              )}
              {(ser.irrigation_mm[day] ?? 0) > 0 && <> · irrigated {Math.round(ser.irrigation_mm[day] as number)} mm</>}
            </>
          ) : (
            <span className="muted">Replay shows daily values</span>
          )}
        </div>
      </div>
    )
  }

  return (
    <section className="card rotations" aria-labelledby="rotations-h" id="rotations">
      <div className="card-head card-head--wide">
        <div className="card-title">
          <h2 id="rotations-h">Compare {run.strategies.length} rotations on the same weather</h2>
          <p>
            Comparison horizon {fullDate.format(start)} – {fullDate.format(end - DAY_MS)}. Hatched seasons are rainfed. Planting
            dates can move ±{MAX_SHIFT_DAYS} days (D6); everything else is fixed.
          </p>
        </div>
        <button type="button" className="switch" role="switch" aria-checked={showRanges} onClick={() => onShowRanges(!showRanges)}>
          <i />
          Show scenario ranges
        </button>
        <span className="rule" />
        <button type="button" className="link" onClick={onExplore}>
          Explore trade-offs ↗
        </button>
      </div>

      <div className="ltl">
        <div className="ltl__axis">
          <span />
          <div className="ltl__ticks" aria-hidden="true">
            {ticks.map((t) => (
              <span key={t} style={{ left: pct(t) }}>
                {monthYear.format(t)}
              </span>
            ))}
          </div>
          <span />
        </div>
        {run.strategies.map(row)}
        {data && (
          <div className="ltl__axis" aria-hidden="true" style={{ position: 'absolute', inset: '18px 0 0 0', pointerEvents: 'none' }}>
            <span />
            <div style={{ position: 'relative', height: '100%' }}>
              {dateIso && <span className="ltl__playhead" style={{ left: pct(ms(dateIso)) }} />}
              {data.turning_point && <span className="ltl__tp" style={{ left: pct(ms(data.turning_point)) }} />}
            </div>
            <span />
          </div>
        )}
      </div>

      {outdated && (
        <p className="small muted">The rows show your edits; the replay and results below still show the last run until you rerun.</p>
      )}
      {pausedAtTurn && data?.turning_point && (
        <div className="replay-note" role="status">
          <span>
            <strong>Paused at a turning point ({fullDate.format(ms(data.turning_point))}):</strong> {data.turning_point_reason}. Try
            moving a planting date or changing the irrigation limit, then run the comparison again.
          </span>
        </div>
      )}
      {trace.status === 'failed' && (
        <StateView kind="failed" title="Replay could not run">
          {trace.error}
        </StateView>
      )}
      {!firstPool && <StateView kind="unavailable">No complete historical window can be replayed for this run.</StateView>}

      <div className="replay" role="group" aria-label="Shared weather replay">
        <button
          type="button"
          className="replay__play"
          aria-label={playing ? 'Pause replay' : 'Play replay'}
          disabled={!data}
          onClick={() => {
            if (!playing && day >= lastDay) setDay(0)
            setPlaying(!playing)
          }}
        >
          {playing ? (
            <>
              <i />
              <i />
            </>
          ) : (
            <Icon src={playIcon} size={16} />
          )}
        </button>
        <div className="replay__run">
          <small>WEATHER OF</small>
          <label className="replay__select replay__year">
            <select
              aria-label="Historical weather window to replay"
              value={years?.join('-') ?? ''}
              onChange={(e) => setYears(e.target.value.split('-').map(Number))}
            >
              {windows.map((w) => (
                <option key={w.years.join('-')} value={w.years.join('-')} disabled={!w.enabled} title={w.reason ?? undefined}>
                  {yearsLabel(w.years)}
                  {w.enabled ? (w.in_sample_pool ? '' : ' · held out, replay only') : ' · unavailable'}
                </option>
              ))}
            </select>
            <Icon src={chevron14} size={14} />
          </label>
        </div>
        <input
          type="range"
          className="scrubber"
          aria-label="Replay date"
          aria-valuetext={dateIso ? fullDate.format(ms(dateIso)) : 'no replay loaded'}
          min={0}
          max={Math.max(lastDay, 1)}
          value={day}
          disabled={!data}
          style={{ '--pct': `${lastDay ? (day / lastDay) * 100 : 0}%` } as CSSProperties}
          onChange={(e) => setDay(Number(e.target.value))}
        />
        <span className="replay__date" title={sourceIso ? `Weather of ${sourceIso}` : undefined}>
          <Icon src={cloudIcon} size={16} />
          {dateIso ? fullDate.format(ms(dateIso)) : trace.status === 'loading' ? 'Loading…' : '—'}
          {data && <small className="muted"> · rain {data.rain_mm[day] == null ? 'missing' : `${data.rain_mm[day]} mm`}</small>}
        </span>
        <label className="replay__select replay__speed">
          <select aria-label="Replay speed" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
          <Icon src={chevron12} size={12} />
        </label>
        <button
          type="button"
          className="btn btn--secondary"
          disabled={!dry}
          title={dry ? `Lowest total rainfall among available windows: ${dry.rain_mm} mm` : 'No window has complete rainfall'}
          onClick={() => dry && setYears(dry.years)}
        >
          Replay a dry year
        </button>
      </div>
      {data && window_ && (
        <p className="small muted">
          Replaying the weather of {yearsLabel(window_.years)}
          {window_.rain_mm != null ? ` (${window_.rain_mm} mm rain)` : ''} on the {fullDate.format(start)} calendar · one path, so no
          range · {window_.in_sample_pool ? 'inside the sample pool' : <Badge tone="warning">held out: replay only</Badge>} · sources{' '}
          {data.source_ids.join(', ')}
        </p>
      )}
    </section>
  )
}

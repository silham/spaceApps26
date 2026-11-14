import { useEffect, useState, type CSSProperties } from 'react'
import alertIcon from '../../assets/v2/icon-alert-14-dark.svg'
import cloudIcon from '../../assets/v2/icon-cloud.svg'
import cropIcon from '../../assets/v2/icon-crop.svg'
import playIcon from '../../assets/v2/icon-play-dark.svg'
import chevron12 from '../../assets/v2/chevron-light-12.svg'
import chevron14 from '../../assets/v2/chevron-light-14.svg'
import dotBaseline from '../../assets/v2/dot-baseline.svg'
import dotSoil from '../../assets/v2/dot-soil.svg'
import dotWater from '../../assets/v2/dot-water.svg'
import { Icon } from '../../components/ui'
import type { StrategyView, Tone } from '../../demo/figmaDemo'

const DAY_MS = 86_400_000
const TICK_MS = 120
const SPEEDS = [1, 2, 4]
const SEASON_LABELS = ['Season 1', 'Between seasons', 'Season 2']
const DOTS: Record<Tone, string> = { baseline: dotBaseline, water: dotWater, soil: dotSoil }

const fullDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const shortDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })

const yearStart = (year: number) => Date.UTC(year, 0, 1)
const dayIndex = (isoDate: string, year: number) =>
  Math.round((Date.parse(`${isoDate}T00:00:00Z`) - yearStart(year)) / DAY_MS)

export interface ReplayCalendar {
  year: number
  startDate: string
  betweenSeasonsStart: string
  seasonTwoStart: string
}

/**
 * "Compare three demo rotations" (Figma node 27:175): three aligned rotation rows and one shared
 * weather replay. The playhead crosses all rows, so every strategy is read against the same day.
 */
export function RotationCompare({
  strategies,
  calendar,
  warning,
  showRanges,
  onShowRanges,
  onExplore,
}: {
  strategies: readonly StrategyView[]
  calendar: ReplayCalendar
  warning: string
  showRanges: boolean
  onShowRanges: (value: boolean) => void
  onExplore: () => void
}) {
  const { year } = calendar
  const lastDay = Math.round((yearStart(year + 1) - yearStart(year)) / DAY_MS) - 1
  const [day, setDay] = useState(() => dayIndex(calendar.startDate, year))
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => setDay((d) => Math.min(d + 1, lastDay)), TICK_MS / speed)
    return () => window.clearInterval(timer)
  }, [playing, speed, lastDay])

  useEffect(() => {
    if (day >= lastDay) setPlaying(false)
  }, [day, lastDay])

  // Timeline columns are equal width whatever their length, so the playhead moves piecewise.
  const bounds: [number, number, number, number] = [
    0,
    dayIndex(calendar.betweenSeasonsStart, year),
    dayIndex(calendar.seasonTwoStart, year),
    lastDay + 1,
  ]
  const seg = day < bounds[1] ? 0 : day < bounds[2] ? 1 : 2
  const segEnd = seg === 0 ? bounds[1] : seg === 1 ? bounds[2] : bounds[3]
  const frac = (day - bounds[seg]) / (segEnd - bounds[seg])
  const date = new Date(yearStart(year) + day * DAY_MS)

  const togglePlay = () => {
    if (!playing && day >= lastDay) setDay(0)
    setPlaying(!playing)
  }

  return (
    <section className="card rotations" aria-labelledby="rotations-h">
      <div className="card-head card-head--wide">
        <div className="card-title">
          <h2 id="rotations-h">Compare three demo rotations</h2>
          <p>Demo crops · local suitability not yet confirmed.</p>
        </div>
        <button
          type="button"
          className="switch"
          role="switch"
          aria-checked={showRanges}
          onClick={() => onShowRanges(!showRanges)}
        >
          <i />
          Show scenario ranges
        </button>
        <span className="rule" />
        <button type="button" className="link" onClick={onExplore}>
          Explore trade-offs ↗
        </button>
      </div>

      <div className="timeline">
        <div className="timeline__row timeline__row--labels">
          <span />
          {SEASON_LABELS.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
        {strategies.map((strategy) => (
          <div key={strategy.id} className="timeline__row">
            <span className="timeline__name">
              <img src={DOTS[strategy.tone]} width={10} height={10} alt="" />
              {strategy.name}
            </span>
            {strategy.cells.map((cell, i) => (
              <span
                key={SEASON_LABELS[i]}
                className={`cell ${cell.glyph === 'crop' ? `cell--${strategy.tone}` : 'cell--none'}${cell.warning ? ' cell--warning' : ''}`}
              >
                {cell.glyph === 'crop' && <Icon src={cropIcon} size={16} />}
                {cell.label}
                {cell.warning && <span className="sr-only"> (warning, see note below)</span>}
              </span>
            ))}
          </div>
        ))}
        <div className="playhead" style={{ '--seg': seg, '--frac': frac } as CSSProperties}>
          <span>{shortDate.format(date)}</span>
        </div>
      </div>

      <p className="rotations__warning">
        <Icon src={alertIcon} size={14} />
        {warning}
      </p>

      <div className="replay" role="group" aria-label="Shared weather replay">
        <button
          type="button"
          className="replay__play"
          aria-label={playing ? 'Pause replay' : 'Play replay'}
          onClick={togglePlay}
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
          <small>PREVIOUS RUN</small>
          <label className="replay__select replay__year">
            <select aria-label="Replay year" value={year} onChange={() => undefined}>
              <option value={year}>{year}</option>
            </select>
            <Icon src={chevron14} size={14} />
          </label>
        </div>
        <input
          type="range"
          className="scrubber"
          aria-label="Replay date"
          aria-valuetext={fullDate.format(date)}
          min={0}
          max={lastDay}
          value={day}
          style={{ '--pct': `${(day / lastDay) * 100}%` } as CSSProperties}
          onChange={(e) => setDay(Number(e.target.value))}
        />
        <span className="replay__date">
          <Icon src={cloudIcon} size={16} />
          {fullDate.format(date)}
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
          aria-disabled="true"
          title="Needs weather data to identify a dry year"
        >
          Replay a dry year
        </button>
      </div>
    </section>
  )
}

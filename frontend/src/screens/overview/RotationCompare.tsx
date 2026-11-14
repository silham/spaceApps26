import { useEffect, useState, type CSSProperties } from 'react'
import { ctl } from '../../components/ctl'
import type { StrategyView } from '../../demo/figmaDemo'

const DAY_MS = 86_400_000
const TICK_MS = 120
const SPEEDS = [1, 2, 4]
const SEASON_LABELS = ['Season 1', 'Between seasons', 'Season 2']

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
 * "Compare three demo rotations" (Figma node 3:161): three aligned rotation rows and one shared
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
  const bounds: [number, number, number, number] = [0, dayIndex(calendar.betweenSeasonsStart, year), dayIndex(calendar.seasonTwoStart, year), lastDay + 1]
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
      <div className="rotations__header">
        <div className="rotations__title">
          <h2 id="rotations-h">Compare three demo rotations</h2>
          <p className="muted">Demo crops · local suitability not yet confirmed.</p>
        </div>
        <div className="rotations__actions">
          <button
            type="button"
            className="link"
            role="switch"
            aria-checked={showRanges}
            onClick={() => onShowRanges(!showRanges)}
          >
            Show scenario ranges  <span aria-hidden="true">{showRanges ? '●' : '○'}</span>
          </button>
          <span aria-hidden="true">{'    |    '}</span>
          <button type="button" className="link" onClick={onExplore}>
            Explore trade-offs ↗
          </button>
        </div>
      </div>

      <div className="timeline">
        <div className="timeline__row">
          <span />
          {SEASON_LABELS.map((label) => (
            <span key={label} className="timeline__season">
              {label}
            </span>
          ))}
        </div>
        {strategies.map((strategy) => (
          <div key={strategy.id} className="timeline__row">
            <span className="timeline__name">
              <span aria-hidden="true">●  </span>
              {strategy.name}
            </span>
            {strategy.cells.map((cell, i) => (
              <span key={SEASON_LABELS[i]} className={`ctl cell cell--${strategy.tone}`}>
                <span aria-hidden="true">{cell.glyph === 'crop' ? '♧  ' : '· · ·  '}</span>
                {cell.label}
                {cell.warning && (
                  <span role="img" aria-label="warning, see note below">
                    {' ⚠'}
                  </span>
                )}
              </span>
            ))}
          </div>
        ))}
        <div className="playhead" style={{ '--seg': seg, '--frac': frac } as CSSProperties}>
          <span className="playhead__label">{shortDate.format(date)}</span>
        </div>
      </div>

      <p className="rotations__warning">⚠ {warning}</p>

      <div className="replay" role="group" aria-label="Shared weather replay">
        <button
          type="button"
          className={ctl('primary')}
          aria-label={playing ? 'Pause replay' : 'Play replay'}
          onClick={togglePlay}
        >
          {playing ? '⏸' : '▶'}
        </button>
        <span className="replay__run">
          {'Previous run   |   '}
          <label className="select select-bare">
            <select aria-label="Replay year" value={year} onChange={() => undefined}>
              <option value={year}>{year}</option>
            </select>
            <span aria-hidden="true"> ⌄</span>
          </label>
        </span>
        <input
          type="range"
          className="scrubber"
          aria-label="Replay date"
          aria-valuetext={fullDate.format(date)}
          min={0}
          max={lastDay}
          value={day}
          onChange={(e) => setDay(Number(e.target.value))}
        />
        <span className="replay__date">
          {`${fullDate.format(date)}   |   `}
          <label className="select select-bare">
            <select aria-label="Replay speed" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
            <span aria-hidden="true"> ⌄</span>
          </label>
        </span>
        <button
          type="button"
          className={ctl('outline')}
          aria-disabled="true"
          title="Needs weather data to identify a dry year"
        >
          Replay a dry year
        </button>
      </div>
    </section>
  )
}

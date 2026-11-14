import dropIcon from '../../assets/v2/icon-drop-20.svg'
import infoIcon from '../../assets/v2/icon-info-16.svg'
import infoIcon18 from '../../assets/v2/icon-info-18.svg'
import leafIcon from '../../assets/v2/icon-leaf-20.svg'
import linkIcon from '../../assets/v2/icon-link.svg'
import trendDown from '../../assets/v2/icon-trend-down.svg'
import trendUp from '../../assets/v2/icon-trend-up.svg'
import { Badge, Icon } from '../../components/ui'
import type { MetricView, PairedDeltaView, StrategyView } from '../../demo/figmaDemo'

const dash = (value: number | null) => (value == null ? '—' : String(value))

function Paired({ paired, reference }: { paired: PairedDeltaView; reference?: undefined }) {
  const benefit = paired.direction === 'benefit'
  return (
    <div className={`paired paired--${paired.direction}`}>
      <p className="paired__title">
        <Icon src={benefit ? trendUp : trendDown} size={16} />
        Potential {paired.direction} · {paired.label}
      </p>
      <p>
        Paired Δ median: {dash(paired.medianDays)} days {' | '} p10–p90: {dash(paired.p10Days)} to{' '}
        {dash(paired.p90Days)}
        <br />
        Better than baseline: {dash(paired.betterPct)}% of paths
      </p>
      {paired.medianDays == null && (
        <Badge tone="neutral" dot={false}>
          Awaiting paired results
        </Badge>
      )}
      {reference}
    </div>
  )
}

function RangeBar({ metric, axis }: { metric: MetricView; axis: [number, number] }) {
  if (metric.p50 == null || metric.p10 == null || metric.p90 == null) return null
  const pos = (v: number) => `${((v - axis[0]) / (axis[1] - axis[0])) * 100}%`
  return (
    <div className="rangebar" aria-hidden="true">
      <span className="rangebar__range" style={{ left: pos(metric.p10), right: `calc(100% - ${pos(metric.p90)})` }} />
      <span className="rangebar__median" style={{ left: pos(metric.p50) }} />
    </div>
  )
}

function Metric({
  icon,
  tile,
  label,
  metric,
  axis,
  showRange,
}: {
  icon: string
  tile: string
  label: string
  metric: MetricView
  axis: [number, number]
  showRange: boolean
}) {
  return (
    <div className="metric">
      <div className="metric__head">
        <span className={`tile ${tile}`}>
          <Icon src={icon} size={20} />
        </span>
        <div className="metric__text">
          <span className="metric__value">{dash(metric.p50)} days</span>
          <span className="metric__label">{label} · typical (median)</span>
        </div>
      </div>
      {showRange && (
        <>
          <RangeBar metric={metric} axis={axis} />
          <p className="range">
            central 80% simulation range (p10–p90): {dash(metric.p10)}–{dash(metric.p90)} days
          </p>
        </>
      )}
    </div>
  )
}

/** "Previous run comparison" (Figma node 28:230): three strategies with aligned metrics. */
export function RunComparison({
  strategies,
  run,
  axes,
  outdated,
  showRanges,
  sourceNote,
  onEvidence,
}: {
  strategies: readonly StrategyView[]
  run: { nPaths: number; sampleStartYear: number; sampleEndYear: number }
  axes: { waterStress: [number, number]; soilCover: [number, number] }
  outdated: boolean
  showRanges: boolean
  sourceNote: readonly string[]
  onEvidence: () => void
}) {
  return (
    <section className="card comparison" aria-labelledby="comparison-h">
      <div className="card-head">
        <div className="comparison__title">
          <h2 id="comparison-h">Previous run comparison</h2>
          {outdated && <Badge tone="warning">Outdated</Badge>}
        </div>
        <div className="comparison__mode">
          Only fixed-allocation metrics shown
          <div className="segmented" role="radiogroup" aria-label="Simulation mode">
            <button type="button" role="radio" aria-checked="true">
              Fixed allocation
            </button>
            <button
              type="button"
              role="radio"
              aria-checked="false"
              aria-disabled="true"
              title="This run has no irrigation-needed results"
            >
              Irrigation needed
            </button>
          </div>
        </div>
      </div>
      <div className="comparison__notes">
        <span>
          Typical = median · central 80% simulation range (p10–p90) {' | '} {run.nPaths} paired weather
          paths · sampled from {run.sampleStartYear}–{run.sampleEndYear}
        </span>
        <Badge tone="info" onClick={onEvidence}>
          Coverage not yet evaluated → Validate
        </Badge>
      </div>
      <p className="comparison__explain">
        <Icon src={infoIcon} size={16} />
        Paired comparisons use matched paths; never subtract strategy medians.
      </p>

      <div className="strategies">
        {strategies.map((strategy) => (
          <article key={strategy.id} className={`strategy strategy--${strategy.tone}`} aria-label={strategy.name}>
            <div className="strategy__accent" />
            <div className="strategy__title">
              <h3>
                <span className="dot" aria-hidden="true" />
                {strategy.name}
              </h3>
              <p>DEMO / illustrative previous-run results</p>
            </div>
            <div className="strategy__body">
              <Metric
                icon={dropIcon}
                tile="tile--info"
                label="Water stress"
                metric={strategy.waterStress}
                axis={axes.waterStress}
                showRange={showRanges}
              />
              {strategy.waterStress.paired ? (
                <Paired paired={strategy.waterStress.paired} />
              ) : (
                <div className="paired">
                  <Badge tone="neutral" dot={false}>
                    Reference · paired Δ = 0
                  </Badge>
                  <p>Paired Δ = strategy − baseline, computed on matching paths.</p>
                </div>
              )}
              <div className="divider" />
              <Metric
                icon={leafIcon}
                tile="tile--success"
                label="Soil cover"
                metric={strategy.soilCover}
                axis={axes.soilCover}
                showRange={showRanges}
              />
              {strategy.soilCover.paired ? (
                <Paired paired={strategy.soilCover.paired} />
              ) : (
                <div className="paired">
                  <Badge tone="neutral" dot={false}>
                    Reference · paired Δ = 0
                  </Badge>
                  <p>Benefit: lower stress; higher cover.</p>
                </div>
              )}
              <div className="divider" />
              <div className="spacer" />
              <div className="strategy__sources">
                <span>
                  {sourceNote[0]}
                  <br />
                  {sourceNote[1]}
                </span>
                <button type="button" className="link" onClick={onEvidence}>
                  Evidence
                  <Icon src={linkIcon} size={13} />
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      <div className="unavailable">
        <Icon src={infoIcon18} size={18} />
        <strong>Heat exposure</strong>
        <Badge tone="neutral">Unavailable</Badge>
        <span>Crop temperature threshold not sourced.</span>
      </div>
    </section>
  )
}

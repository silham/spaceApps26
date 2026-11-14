import infoIcon from '../../assets/icon-info-22.svg'
import leafIcon from '../../assets/icon-leaf-28.svg'
import waterIcon from '../../assets/icon-water-28.svg'
import { ctl } from '../../components/ctl'
import type { MetricView, PairedDeltaView, StrategyView } from '../../demo/figmaDemo'

const dash = (value: number | null) => (value == null ? '—' : String(value))

function Paired({ paired }: { paired: PairedDeltaView }) {
  const benefit = paired.direction === 'benefit'
  return (
    <div className={`paired paired--${paired.direction}`}>
      <p className="paired__title">
        <span aria-hidden="true">{benefit ? '♧' : '⚠'} </span>
        Potential {paired.direction} · {paired.label}
      </p>
      <p className="paired__text">
        Paired Δ median: {dash(paired.medianDays)} days | p10–p90: {dash(paired.p10Days)} to {dash(paired.p90Days)}
        <br />
        Better than baseline: {dash(paired.betterPct)}% of paths
      </p>
      {paired.medianDays == null && <span className={ctl('neutral')}>Awaiting paired results</span>}
    </div>
  )
}

function Metric({
  icon,
  label,
  metric,
  showRange,
}: {
  icon: string
  label: string
  metric: MetricView
  showRange: boolean
}) {
  return (
    <>
      <div className="metric">
        <img src={icon} width={28} height={28} alt="" />
        <div className="metric__text">
          <span className="metric__value">{dash(metric.p50)} days</span>
          <span className="metric__label">{label} · typical (median)</span>
        </div>
      </div>
      {showRange && (
        <p className="range">
          central 80% simulation range (p10–p90): {dash(metric.p10)}–{dash(metric.p90)} days
        </p>
      )}
      {metric.paired ? (
        <Paired paired={metric.paired} />
      ) : (
        <>
          <span className={ctl('neutral')}>ⓘ  Reference · paired Δ = 0</span>
          <div className="reference-gap" />
        </>
      )}
      <div className="divider" />
    </>
  )
}

/** "Previous run comparison" (Figma node 3:208): three strategies with aligned metrics. */
export function RunComparison({
  strategies,
  run,
  outdated,
  showRanges,
  sourceNote,
  onEvidence,
}: {
  strategies: readonly StrategyView[]
  run: { nPaths: number; sampleStartYear: number; sampleEndYear: number }
  outdated: boolean
  showRanges: boolean
  sourceNote: readonly string[]
  onEvidence: () => void
}) {
  return (
    <section className="card comparison" aria-labelledby="comparison-h">
      <div className="comparison__heading">
        <h2 id="comparison-h">Previous run comparison</h2>
        {outdated && <span className={ctl('warning')}>outdated</span>}
      </div>
      <div className="comparison__mode" role="radiogroup" aria-label="Simulation mode">
        <button type="button" role="radio" aria-checked="true" className={ctl('primary')}>
          ◉  Fixed allocation
        </button>
        <button
          type="button"
          role="radio"
          aria-checked="false"
          aria-disabled="true"
          title="This run has no irrigation-needed results"
          className={ctl('outline')}
        >
          ○  Irrigation needed
        </button>
        <span className="pre">{'  |    Only fixed-allocation metrics shown'}</span>
      </div>
      <div className="divider" />
      <p className="comparison__summary pre">
        {`Typical = median  ·  central 80% simulation range (p10–p90)   |   ${run.nPaths} paired weather paths · sampled from ${run.sampleStartYear}–${run.sampleEndYear}`}
      </p>
      <button type="button" className={ctl('evidence')} onClick={onEvidence}>
        ⓘ Coverage not yet evaluated → Validate
      </button>
      <p className="comparison__note">Paired comparisons use matched paths; never subtract strategy medians.</p>

      <div className="strategies">
        {strategies.map((strategy) => (
          <article key={strategy.id} className="card strategy" aria-label={strategy.name}>
            <div className={`strategy__title strategy__title--${strategy.tone}`}>
              <h3>
                <span aria-hidden="true">●  </span>
                {strategy.name}
              </h3>
              <p>DEMO / illustrative previous-run results</p>
            </div>
            <Metric icon={waterIcon} label="Water stress" metric={strategy.waterStress} showRange={showRanges} />
            <Metric icon={leafIcon} label="Soil cover" metric={strategy.soilCover} showRange={showRanges} />
            {strategy.tone === 'baseline' && (
              <p className="strategy__explain">
                Paired Δ = strategy − baseline, computed on matching paths.
                <br />
                Benefit: lower stress; higher cover.
              </p>
            )}
            <p className="strategy__sources">
              {sourceNote[0]}
              <br />
              {sourceNote[1]}
            </p>
            <button type="button" className="link" onClick={onEvidence}>
              Evidence ↗
            </button>
          </article>
        ))}
      </div>

      <div className="unavailable">
        <img src={infoIcon} width={22} height={22} alt="" />
        <p>Heat exposure · Unavailable — crop temperature threshold not sourced.</p>
      </div>
    </section>
  )
}

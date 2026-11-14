import type { ReactNode } from 'react'
import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { DemoBadge } from '../components/DemoBadge'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Badge } from '../components/ui'
import { KIND_TONE, STAGES, STATUS } from '../journey'
import { CoverageStrip, GapMarkers, MissingTimeline, ObservedVsDetected, RawVsClean, ViCurveChart } from '../journey/charts'
import { FootprintMap } from '../journey/FootprintMap'
import { chartType, detailStrings, readFootprints } from '../journey/payloads'
import type { JourneyStage } from '../types/contracts'

interface SourceInfo {
  source_id: string
  provider?: string
  product?: string
  version?: string | null
  license?: string | null
  doi?: string | null
  spatial_resolution?: string | null
  temporal_resolution?: string | null
  limitations?: string | null
}

/** Source details live in Collect's `details.sources`; every other card looks its IDs up there. */
function sourceIndex(stages: JourneyStage[]): Map<string, SourceInfo> {
  const rows = stages.find((s) => s.stage === 'collect')?.details?.sources
  const list = Array.isArray(rows) ? (rows as SourceInfo[]) : []
  return new Map(list.map((r) => [r.source_id, r]))
}

interface DeltaRow { strategy: string; metric: string; unit: string; p10: number | null; p50: number | null; p90: number | null; share_better: number | null }
function PairedDeltasChart({ stage }: { stage: JourneyStage }) {
  const rows = Array.isArray(stage.chart?.rows) ? (stage.chart.rows as DeltaRow[]) : null
  if (!rows) return <p className="muted small">Comparison data arrived in an unexpected form, so nothing is drawn.</p>
  const n = (v: number | null) => (v == null ? '—' : Math.round(v).toLocaleString('en-GB'))
  return (
    <div className="table-wrap">
      <table className="metrics-table">
        <caption className="small muted">{String(stage.chart?.title ?? '')}</caption>
        <thead><tr><th scope="col">Strategy</th><th scope="col">Metric</th><th scope="col">Median Δ</th><th scope="col">p10 to p90</th><th scope="col">Better on</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.strategy}-${r.metric}`}>
              <td>{r.strategy}</td><td>{r.metric.replace(/_/g, ' ')}</td>
              <td className="num">{n(r.p50)} {r.unit}</td><td className="num">{n(r.p10)} to {n(r.p90)}</td>
              <td className="num">{r.share_better == null ? '—' : `${Math.round(r.share_better * 100)}% of paths`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StageChart({ stage }: { stage: JourneyStage }) {
  switch (chartType(stage)) {
    case 'coverage_strip': return <CoverageStrip stage={stage} />
    case 'missing_timeline': return <MissingTimeline stage={stage} />
    case 'raw_vs_clean': return <RawVsClean stage={stage} />
    case 'gap_markers': return <GapMarkers stage={stage} />
    case 'vi_curve': return <ViCurveChart stage={stage} />
    case 'observed_vs_detected': return <ObservedVsDetected stage={stage} />
    case 'paired_deltas': return <PairedDeltasChart stage={stage} />
    case 'footprint_map': {
      const features = readFootprints(stage)
      return features ? <FootprintMap features={features} /> : <p className="muted small">Map data arrived in an unexpected form, so nothing is drawn.</p>
    }
    default:
      return null
  }
}

const Bullets = ({ title, items }: { title: string; items: string[] }) =>
  items.length === 0 ? null : (
    <div className="detail-block">
      <h3>{title}</h3>
      <ul className="list list--tight small">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </div>
  )

/** Stage-specific notes. Failures and not-yet-evaluated items are part of the honest result, so they are never folded away. */
function StageDetails({ stage, sources }: { stage: JourneyStage; sources: Map<string, SourceInfo> }) {
  const qa = stage.details?.satellite_vegetation_qa
  const reference = stage.details?.reference
  const independence = stage.details?.independence_notes
  const blocks: ReactNode[] = []
  if (stage.stage === 'check' && qa && typeof qa === 'object') {
    blocks.push(
      <div className="detail-block" key="qa">
        <h3>Satellite vegetation quality flags</h3>
        <dl className="kv small">
          {Object.entries(qa as Record<string, unknown>).map(([k, v]) => (
            <div key={k}><dt>{k.replace(/_/g, ' ')}</dt><dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd></div>
          ))}
        </dl>
      </div>,
    )
  }
  if (stage.stage === 'collect') {
    blocks.push(<Bullets key="missing" title="Not collected" items={detailStrings(stage, 'missing')} />)
    if (sources.size > 0) {
      blocks.push(
        <details key="src" className="detail-block">
          <summary>Source details ({sources.size})</summary>
          <ul className="list small">
            {[...sources.values()].map((s) => <SourceLine key={s.source_id} s={s} />)}
          </ul>
        </details>,
      )
    }
  }
  if (stage.stage === 'extract') {
    blocks.push(<Bullets key="cav" title="Things to keep in mind" items={detailStrings(stage, 'caveats')} />)
  }
  if (stage.stage === 'validate') {
    if (typeof reference === 'string') blocks.push(<p key="ref" className="small muted">Reference: {reference}</p>)
    blocks.push(<Bullets key="fail" title="Failures" items={detailStrings(stage, 'failures')} />)
    blocks.push(<Bullets key="nye" title="Not yet evaluated" items={detailStrings(stage, 'not_yet_evaluated')} />)
    if (typeof independence === 'string' && independence) blocks.push(<p key="ind" className="small muted">Independence: {independence}</p>)
  }
  return <>{blocks}</>
}

function SourceLine({ s }: { s: SourceInfo }) {
  const bits = [s.provider, s.version && `version ${s.version}`, s.spatial_resolution, s.temporal_resolution, s.license && `licence: ${s.license}`, s.doi && `DOI ${s.doi}`].filter(Boolean)
  return (
    <li>
      <strong>{s.product ?? s.source_id}</strong> <span className="muted">({s.source_id})</span>
      <div className="muted">{bits.join(' · ')}</div>
      {s.limitations && <div>Limitations: {s.limitations}</div>}
    </li>
  )
}

/** Rule 2: every chart carries the IDs of the sources it used and its processing run. */
function SourceFooter({ stage, sources }: { stage: JourneyStage; sources: Map<string, SourceInfo> }) {
  const ids = stage.source_ids ?? []
  return (
    <footer className="stage__sources small muted">
      <div>
        Sources: {ids.length ? ids.join(', ') : 'none recorded'}
        {stage.processing_run_id ? ` · run ${stage.processing_run_id}` : ''}
      </div>
      {ids.some((id) => sources.has(id)) && stage.stage !== 'collect' && (
        <details>
          <summary>What these sources are</summary>
          <ul className="list small">
            {ids.filter((id) => sources.has(id)).map((id) => <SourceLine key={id} s={sources.get(id) as SourceInfo} />)}
          </ul>
        </details>
      )}
    </footer>
  )
}

/**
 * Data Journey: nine stage cards, one chart each. No Figma frame exists for this view yet; it reuses
 * the dashboard's card and status-badge patterns. Stages the API does not report show "Unavailable".
 */
export function DataJourneyScreen({ siteId }: { siteId: string | undefined }) {
  const journey = useAsync(
    () => (siteId ? api.journey(siteId) : Promise.reject(new Error('no site is available from the API'))),
    [siteId],
  )
  const stages = journey.status === 'ready' ? journey.data : []
  const sources = sourceIndex(stages)
  return (
    <>
      <h1 className="page-title">Data Journey</h1>
      {journey.status === 'loading' && <p role="status">Loading pipeline status…</p>}
      {journey.status === 'error' && (
        <p role="alert" className="alert">
          ⚠ Pipeline status could not be loaded: {journey.error.message}
        </p>
      )}
      <ol className="journey">
        {STAGES.map((def, i) => {
          const payload = stages.find((s) => s.stage === def.id)
          const status = STATUS[payload?.status ?? 'unavailable']
          return (
            <li key={def.id} className="card page-card stage" aria-labelledby={`stage-${def.id}`}>
              <div className="row">
                <span className="stage__n" aria-hidden="true">{i + 1}</span>
                <h2 id={`stage-${def.id}`}>{def.label}</h2>
                <Badge tone={KIND_TONE[status.kind]}>{status.label}</Badge>
                {payload?.is_demo && <DemoBadge />}
              </div>
              <p className="muted">{def.question}</p>
              <details className="detail-block">
                <summary>What does this mean?</summary>
                <p className="small">{def.meaning}</p>
              </details>
              {payload && <p>{payload.summary}</p>}
              {payload && (
                <ErrorBoundary what="This chart">
                  <StageChart stage={payload} />
                </ErrorBoundary>
              )}
              {payload && <StageDetails stage={payload} sources={sources} />}
              {payload && <SourceFooter stage={payload} sources={sources} />}
            </li>
          )
        })}
      </ol>
    </>
  )
}

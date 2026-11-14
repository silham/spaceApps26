import { useState } from 'react'
import { api } from '../../api/client'
import { useAsync } from '../../api/useAsync'
import warnIcon from '../../assets/icon-warn.svg'
import { SelectControl } from '../../components/Control'
import { ctl } from '../../components/ctl'
import { DemoBadge } from '../../components/DemoBadge'
import { figmaDemo as demo } from '../../demo/figmaDemo'
import type { View } from '../../layout/Sidebar'
import type { JourneyStageName, Site, StageStatus } from '../../types/contracts'
import { FieldMap } from './FieldMap'
import { JourneySummary } from './JourneySummary'
import { NextStep } from './NextStep'
import { PrioritiesPanel, type Priorities } from './PrioritiesPanel'
import { RotationCompare } from './RotationCompare'
import { RunComparison } from './RunComparison'

type RunState = { status: 'idle' } | { status: 'running' } | { status: 'failed'; message: string }

const joinList = (items: string[]) =>
  items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`

/**
 * Overview dashboard: Figma frame 3:2. Site list and pipeline statuses come from the API when it
 * provides them; everything else is the frame's illustrative content from demo/figmaDemo.ts and is
 * labelled DEMO on screen.
 */
export function OverviewScreen({
  sites,
  site,
  onSiteChange,
  onNavigate,
}: {
  sites: Site[]
  site: Site | undefined
  onSiteChange: (siteId: string) => void
  onNavigate: (view: View) => void
}) {
  const [priorities, setPriorities] = useState<Priorities>(demo.priorities)
  const [marketCrop, setMarketCrop] = useState<boolean>(demo.constraints.mustIncludeMarketCrop)
  const [showRanges, setShowRanges] = useState(true)
  const [run, setRun] = useState<RunState>({ status: 'idle' })

  const siteId = site?.id
  const journey = useAsync(
    () => (siteId ? api.journey(siteId) : Promise.reject(new Error('No site selected'))),
    [siteId],
  )
  const liveJourney = journey.status === 'ready' && journey.data.length > 0
  const statuses: [JourneyStageName, StageStatus][] = liveJourney
    ? journey.data.map((stage) => [stage.stage, stage.status])
    : demo.journey

  // Anything edited since the previous run makes its results outdated until a rerun succeeds.
  const changed = [
    ...demo.changedSinceRun,
    ...(marketCrop !== demo.constraints.mustIncludeMarketCrop ? ['market-crop requirement'] : []),
  ]
  const outdated = changed.length > 0

  const runComparison = () => {
    setRun({ status: 'running' })
    api.createRun().then(
      // TODO(M2 with M1/M4): load the new run's results and clear `changed` once POST /runs exists.
      () => setRun({ status: 'idle' }),
      (error: Error) => setRun({ status: 'failed', message: error.message }),
    )
  }

  const farmOptions =
    sites.length > 0
      ? sites.map((s) => ({ value: s.id, label: s.name }))
      : [{ value: '', label: demo.farmLabel }]

  return (
    <>
      <div className="header">
        <div className="header__title">
          <h1>Your farm. Different futures.</h1>
          <p>Compare rotations under the same weather conditions.</p>
        </div>
        <SelectControl label="Farm" value={siteId ?? ''} options={farmOptions} onChange={onSiteChange} />
        <SelectControl
          label="Display window"
          prefix="Display window: "
          value={demo.displayWindow}
          options={[{ value: demo.displayWindow, label: demo.displayWindow }]}
        />
        {demo.isDemo && <DemoBadge />}
        <button type="button" className={ctl('primary')} disabled={run.status === 'running'} onClick={runComparison}>
          {run.status === 'running' ? 'Running…' : '▶  Run comparison'}
        </button>
      </div>

      {outdated && (
        <div className="banner" role="status">
          <img src={warnIcon} width={22} height={22} alt="" />
          <p className="banner__text">
            Results outdated — {joinList(changed)} changed. Run comparison to refresh.
          </p>
          <div className="banner__gap" />
          <p className="banner__run">Previous run {demo.run.id}</p>
        </div>
      )}
      {run.status === 'failed' && (
        <p className="run-error" role="alert">
          ⚠ Comparison did not run: {run.message}. The results below are unchanged.
        </p>
      )}

      <div className="sampling">
        <p className="sampling__main">
          {`Weather sampling: ${demo.run.sampleStartYear}–${demo.run.sampleEndYear}  ·  ${demo.run.nPaths} paired paths  ·  ${demo.run.horizonYears}-year horizon`}
        </p>
        <p className="sampling__sub">{demo.run.excludedNote}</p>
      </div>

      <JourneySummary statuses={statuses} illustrative={!liveJourney} onInspect={() => onNavigate('journey')} />

      <div className="field-row">
        <FieldMap fieldLabel={demo.field.label} onViewSource={() => onNavigate('evidence')} />
        <PrioritiesPanel
          priorities={priorities}
          onPriorities={setPriorities}
          constraints={demo.constraints}
          irrigationChanged={changed.includes('irrigation limit')}
          marketCrop={marketCrop}
          onMarketCrop={setMarketCrop}
        />
      </div>

      <RotationCompare
        strategies={demo.strategies}
        calendar={demo.replay}
        warning={demo.rotationWarning}
        showRanges={showRanges}
        onShowRanges={setShowRanges}
        onExplore={() => onNavigate('rotation')}
      />

      <RunComparison
        strategies={demo.strategies}
        run={demo.run}
        outdated={outdated}
        showRanges={showRanges}
        sourceNote={demo.metricSourceNote}
        onEvidence={() => onNavigate('evidence')}
      />

      <NextStep strategies={demo.strategies} outdated={outdated} />

      <footer className="source-footer">
        <strong>{demo.sourceFooter}</strong>
        <span>Design concept — provided Figma frames supersede this mockup.</span>
      </footer>
    </>
  )
}

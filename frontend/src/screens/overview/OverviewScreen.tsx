import { useState } from 'react'
import { api } from '../../api/client'
import { useAsync } from '../../api/useAsync'
import alertIcon from '../../assets/v2/icon-alert-20.svg'
import branchIcon from '../../assets/v2/icon-branch.svg'
import calendarIcon from '../../assets/v2/icon-calendar.svg'
import clockIcon from '../../assets/v2/icon-clock.svg'
import infoIcon from '../../assets/v2/icon-info-18.svg'
import playIcon from '../../assets/v2/icon-play.svg'
import { DemoBadge } from '../../components/DemoBadge'
import { Icon, SelectControl } from '../../components/ui'
import { figmaDemo as demo } from '../../demo/figmaDemo'
import type { View } from '../../layout/Sidebar'
import type { JourneyStageName, Site, StageStatus } from '../../types/contracts'
import { FieldMap } from './FieldMap'
import { JourneySummary } from './JourneySummary'
import { NextStep } from './NextStep'
import { PrioritiesPanel, type Priorities } from './PrioritiesPanel'
import { RotationCompare } from './RotationCompare'
import { RunComparison } from './RunComparison'
import { LiveOverview } from './LiveOverview'

type RunState = { status: 'idle' } | { status: 'running' } | { status: 'failed'; message: string }

const joinList = (items: string[]) =>
  items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/**
 * Overview dashboard: Figma frame 25:49 (Redesign v2). A loaded (non-DEMO) farm gets the live
 * dashboard; with no API or a DEMO site it shows the frame's illustrative content, labelled DEMO.
 */
export function OverviewScreen(props: {
  sites: Site[]
  site: Site | undefined
  onSiteChange: (siteId: string) => void
  onNavigate: (view: View) => void
}) {
  if (props.site && !props.site.is_demo) return <LiveOverview {...props} site={props.site} />
  return <DemoOverview {...props} />
}

function DemoOverview({
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

  // The DEMO farm has no strategies of its own, so a run is attempted and its refusal shown honestly.
  const runComparison = () => {
    if (!siteId) {
      setRun({ status: 'failed', message: 'no farm is available from the API (DEMO content only)' })
      return
    }
    setRun({ status: 'running' })
    api.createRun({ site_id: siteId }).then(
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
          <div className="header__subtitle">
            {demo.isDemo && <DemoBadge />}
            <span>Compare rotations under the same weather conditions.</span>
          </div>
        </div>
        <div className="header__controls">
          <SelectControl label="Farm" value={siteId ?? ''} options={farmOptions} onChange={onSiteChange} />
          <SelectControl
            label="Display window"
            prefix="Display window: "
            value={demo.displayWindow}
            options={[{ value: demo.displayWindow, label: demo.displayWindow }]}
          />
          <button type="button" className="btn btn--primary" disabled={run.status === 'running'} onClick={runComparison}>
            <Icon src={playIcon} size={14} />
            {run.status === 'running' ? 'Running…' : 'Run comparison'}
          </button>
        </div>
      </div>

      {outdated && (
        <div className="banner" role="status">
          <span className="tile">
            <Icon src={alertIcon} size={20} />
          </span>
          <div className="banner__text">
            <strong>Results outdated</strong>
            <span>{capitalise(joinList(changed))} changed. Run comparison to refresh.</span>
          </div>
          <span className="banner__run">Previous run {demo.run.id}</span>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={run.status === 'running'}
            onClick={runComparison}
          >
            Refresh results
          </button>
        </div>
      )}
      {run.status === 'failed' && (
        <p className="run-error" role="alert">
          ⚠ Comparison did not run: {run.message}. The results below are unchanged.
        </p>
      )}

      <div className="stats">
        <div className="stat">
          <span className="tile tile--leaf">
            <Icon src={calendarIcon} size={20} />
          </span>
          <div className="stat__text">
            <strong>
              {demo.run.sampleStartYear}–{demo.run.sampleEndYear}
            </strong>
            <span>Weather sampling window</span>
          </div>
        </div>
        <div className="stat">
          <span className="tile tile--info">
            <Icon src={branchIcon} size={20} />
          </span>
          <div className="stat__text">
            <strong>{demo.run.nPaths}</strong>
            <span>Paired weather paths</span>
          </div>
        </div>
        <div className="stat">
          <span className="tile tile--violet">
            <Icon src={clockIcon} size={20} />
          </span>
          <div className="stat__text">
            <strong>{demo.run.horizonYears} years</strong>
            <span>Simulation horizon</span>
          </div>
        </div>
        <div className="stat stat--note">
          <Icon src={infoIcon} size={18} />
          {demo.run.excludedNote}
        </div>
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
        axes={demo.axes}
        outdated={outdated}
        showRanges={showRanges}
        sourceNote={demo.metricSourceNote}
        onEvidence={() => onNavigate('evidence')}
      />

      <NextStep strategies={demo.strategies} outdated={outdated} />

      <footer className="source-footer">
        <span>{demo.sourceFooter}</span>
        <span>Design concept — provided Figma frames supersede this mockup.</span>
      </footer>
    </>
  )
}

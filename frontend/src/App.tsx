import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import { useAsync } from './api/useAsync'
import chevronRight from './assets/v2/chevron-right.svg'
import { Badge, Icon, type Tone } from './components/ui'
import { figmaDemo } from './demo/figmaDemo'
import { Sidebar, type View } from './layout/Sidebar'
import { DataJourneyScreen } from './screens/DataJourneyScreen'
import { EvidenceScreen } from './screens/EvidenceScreen'
import { OverviewScreen } from './screens/overview/OverviewScreen'
import { RotationPlannerScreen } from './screens/RotationPlannerScreen'

export default function App() {
  const [view, setView] = useState<View>('overview')
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null)
  const mainRef = useRef<HTMLElement>(null)
  const health = useAsync(api.health, [])
  const sites = useAsync(api.sites, [])

  const siteList = sites.status === 'ready' ? sites.data : []
  const site = siteList.find((s) => s.id === selectedSiteId) ?? siteList[0]

  // Move focus to the new view's heading so keyboard and screen-reader users land on the content.
  useEffect(() => {
    mainRef.current?.querySelector<HTMLElement>('h1')?.focus({ preventScroll: true })
  }, [view])

  // The frame shows "Saved just now" here, but nothing is saved yet, so this badge reports the API
  // connection instead (docs/decisions.md, UI assumptions).
  const apiStatus: { tone: Tone; label: string } =
    health.status === 'ready'
      ? { tone: 'success', label: 'API connected' }
      : health.status === 'error'
        ? { tone: 'warning', label: 'API unreachable' }
        : { tone: 'neutral', label: 'Connecting…' }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to main content</a>
      <Sidebar view={view} onNavigate={setView} />
      <div className="content">
        <div className="topbar">
          <div className="topbar__crumbs">
            <span>My farms</span>
            <Icon src={chevronRight} size={14} />
            <strong>{site?.name ?? figmaDemo.farmLabel}</strong>
          </div>
          <span role="status">
            <Badge tone={apiStatus.tone}>{apiStatus.label}</Badge>
          </span>
        </div>
        <main className="main" id="main" tabIndex={-1} ref={mainRef}>
          {view === 'overview' && (
            <OverviewScreen sites={siteList} site={site} onSiteChange={setSelectedSiteId} onNavigate={setView} />
          )}
          {view === 'rotation' && <RotationPlannerScreen siteId={site?.id} />}
          {view === 'journey' && <DataJourneyScreen siteId={site?.id} />}
          {view === 'evidence' && <EvidenceScreen siteId={site?.id} />}
        </main>
      </div>
    </div>
  )
}

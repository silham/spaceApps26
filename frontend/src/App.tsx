import { useState } from 'react'
import { api } from './api/client'
import { useAsync } from './api/useAsync'
import { figmaDemo } from './demo/figmaDemo'
import { Sidebar, type View } from './layout/Sidebar'
import { DataJourneyScreen } from './screens/DataJourneyScreen'
import { EvidenceScreen } from './screens/EvidenceScreen'
import { OverviewScreen } from './screens/overview/OverviewScreen'
import { RotationPlannerScreen } from './screens/RotationPlannerScreen'

// DEMO run ID from data/fixtures/demo.json until run selection exists (M2/M1).
const DEMO_RUN_ID = 'demo-run'

export default function App() {
  const [view, setView] = useState<View>('overview')
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null)
  const health = useAsync(api.health, [])
  const sites = useAsync(api.sites, [])

  const siteList = sites.status === 'ready' ? sites.data : []
  const site = siteList.find((s) => s.id === selectedSiteId) ?? siteList[0]

  // The frame shows "Saved just now" here, but nothing is saved yet, so this slot reports the API
  // connection instead (docs/decisions.md, UI assumptions).
  const apiStatus =
    health.status === 'ready' ? 'API connected' : health.status === 'error' ? 'API unreachable' : 'Connecting…'

  return (
    <div className="shell">
      <Sidebar view={view} onNavigate={setView} />
      <div className="content">
        <div className="breadcrumb">
          <span className="breadcrumb__path">{`My farms   /   ${site?.name ?? figmaDemo.farmLabel}`}</span>
          <span className="breadcrumb__gap" />
          <span className="breadcrumb__status" role="status">
            {apiStatus}
            <span aria-hidden="true">{'    |    ●'}</span>
          </span>
        </div>
        <main className="main">
          {view === 'overview' && (
            <OverviewScreen sites={siteList} site={site} onSiteChange={setSelectedSiteId} onNavigate={setView} />
          )}
          {view === 'rotation' && <RotationPlannerScreen siteId={site?.id} />}
          {view === 'journey' && <DataJourneyScreen siteId={site?.id} />}
          {view === 'evidence' && <EvidenceScreen runId={DEMO_RUN_ID} />}
        </main>
      </div>
    </div>
  )
}

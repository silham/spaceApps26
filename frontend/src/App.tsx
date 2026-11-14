import { useState } from 'react'
import { api } from './api/client'
import { useAsync } from './api/useAsync'
import { DataJourneyScreen } from './screens/DataJourneyScreen'
import { DecideScreen } from './screens/DecideScreen'
import { ExperimentScreen } from './screens/ExperimentScreen'
import { ObserveScreen } from './screens/ObserveScreen'

const TABS = ['Observe', 'Experiment', 'Decide', 'Data Journey'] as const
type Tab = (typeof TABS)[number]

// DEMO IDs from data/fixtures/demo.json until site selection exists (M2/M1).
const DEMO_SITE_ID = 'demo-site'
const DEMO_RUN_ID = 'demo-run'

export default function App() {
  const [tab, setTab] = useState<Tab>('Observe')
  const health = useAsync(api.health, [])

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 'var(--space-6)' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1 style={{ color: 'var(--color-primary)' }}>Farm Time Machine</h1>
        <small>
          {health.status === 'ready'
            ? `API ${health.data.api_version} · model ${health.data.model_version}`
            : health.status === 'error'
              ? 'API unreachable. Run `make api`.'
              : 'Connecting…'}
        </small>
      </header>
      <nav aria-label="Steps" role="tablist" style={{ display: 'flex', gap: 'var(--space-2)' }}>
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
      <main>
        {tab === 'Observe' && <ObserveScreen />}
        {tab === 'Experiment' && <ExperimentScreen siteId={DEMO_SITE_ID} />}
        {tab === 'Decide' && <DecideScreen runId={DEMO_RUN_ID} />}
        {tab === 'Data Journey' && <DataJourneyScreen />}
      </main>
    </div>
  )
}

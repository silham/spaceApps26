import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api/client'
import { useAsync } from './api/useAsync'
import chevronRight from './assets/v2/chevron-right.svg'
import { StateView } from './components/StateView'
import { Badge, Icon, type Tone } from './components/ui'
import { Sidebar, type View } from './layout/Sidebar'
import { DataJourneyScreen } from './screens/DataJourneyScreen'
import { AccountScreen } from './screens/AccountScreen'
import { AuthScreen } from './screens/AuthScreen'
import { FarmsScreen } from './screens/FarmsScreen'
import { EvidenceScreen } from './screens/EvidenceScreen'
import { OverviewScreen } from './screens/overview/OverviewScreen'
import { RotationPlannerScreen } from './screens/RotationPlannerScreen'
import type { Site, User } from './types/contracts'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [checked, setChecked] = useState(false)
  const [error, setError] = useState('')
  const [expired, setExpired] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    api.me().then(
      (value) => {
        if (active) {
          setUser(value)
          setChecked(true)
        }
      },
      (err: unknown) => {
        if (!active) return
        if (err instanceof ApiError && err.status === 401) setChecked(true)
        else setError('Could not reach the Farm Time Machine API. Check that it is running, then try again.')
      },
    )
    return () => {
      active = false
    }
  }, [attempt])
  // Any 401 from the API (expired or revoked session) sends the user back to sign in.
  useEffect(() => {
    const onExpired = () =>
      setUser((current) => {
        if (current) setExpired(true)
        return null
      })
    window.addEventListener('ftm-session-expired', onExpired)
    return () => window.removeEventListener('ftm-session-expired', onExpired)
  }, [])

  if (!checked)
    return (
      <div className="auth-splash">
        {error ? (
          <StateView kind="failed" title="Cannot connect">
            {error}
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => {
                setError('')
                setAttempt((v) => v + 1)
              }}
            >
              Try again
            </button>
          </StateView>
        ) : (
          <StateView kind="loading" title="Checking your session…" />
        )}
      </div>
    )
  if (!user)
    return (
      <AuthScreen
        notice={expired ? 'Your session has ended. Sign in again to continue.' : undefined}
        onSignedIn={(u) => {
          setExpired(false)
          setUser(u)
        }}
      />
    )
  return <Workspace key={user.id} user={user} onUserChange={setUser} />
}

function Workspace({ user, onUserChange }: { user: User; onUserChange: (user: User | null) => void }) {
  const [view, setView] = useState<View>('farms')
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null)
  const mainRef = useRef<HTMLElement>(null)
  const health = useAsync(api.health, [])
  const [sitesVersion, setSitesVersion] = useState(0)
  const sites = useAsync(api.sites, [sitesVersion])

  // The last loaded list stays in use while a refresh is in flight, so open views are not torn down.
  const [loadedSites, setLoadedSites] = useState<Site[] | null>(null)
  useEffect(() => {
    if (sites.status === 'ready') setLoadedSites(sites.data)
  }, [sites])
  const siteList = loadedSites ?? []
  // Every farm belongs to this account (D14). Default to the first one; none means the farm views ask for one.
  const site = siteList.find((s) => s.id === selectedSiteId) ?? siteList.find((s) => !s.is_demo) ?? siteList[0]
  const openFarm = (id: string) => {
    setSelectedSiteId(id)
    setSitesVersion((n) => n + 1)
    setView('overview')
  }
  const farmView = view === 'overview' || view === 'rotation' || view === 'journey' || view === 'evidence'

  // Move focus to the new view's heading so keyboard and screen-reader users land on the content
  // (not on first load, where the browser would draw a focus ring on the heading).
  const navigated = useRef(false)
  useEffect(() => {
    if (navigated.current) mainRef.current?.querySelector<HTMLElement>('h1')?.focus({ preventScroll: true })
    navigated.current = true
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
      <Sidebar view={view} onNavigate={setView} user={user} />
      <div className="content">
        <div className="topbar">
          <div className="topbar__crumbs">
            <button type="button" className="topbar__home" onClick={() => setView('farms')}>
              My farms
            </button>
            {view !== 'farms' && view !== 'account' && site && (
              <>
                <Icon src={chevronRight} size={14} />
                <strong>{site.name}</strong>
              </>
            )}
            {view === 'account' && (
              <>
                <Icon src={chevronRight} size={14} />
                <strong>Your account</strong>
              </>
            )}
          </div>
          <span role="status">
            <Badge tone={apiStatus.tone}>{apiStatus.label}</Badge>
          </span>
        </div>
        <main className="main" id="main" tabIndex={-1} ref={mainRef}>
          {view === 'account' && <AccountScreen user={user} onUserChange={onUserChange} />}
          {view === 'farms' && (
            <FarmsScreen currentSiteId={site?.id} onOpen={openFarm} onChange={() => setSitesVersion((v) => v + 1)} />
          )}
          {farmView && loadedSites === null && sites.status === 'loading' && <StateView kind="loading" title="Loading your farms…" />}
          {farmView && loadedSites === null && sites.status === 'error' && (
            <StateView kind="failed" title="Could not load your farms">
              {sites.error.message}
            </StateView>
          )}
          {farmView && loadedSites !== null && !site && (
            <div className="no-farm">
              <h1 className="page-title" tabIndex={-1}>
                No farm yet
              </h1>
              <StateView kind="empty" title="Add a farm to get started">
                Its field history, Data Journey and evidence appear here once its data has loaded.
                <button type="button" className="btn btn--primary" onClick={() => setView('farms')}>
                  Go to My farms
                </button>
              </StateView>
            </div>
          )}
          {site && view === 'overview' && (
            <OverviewScreen sites={siteList} site={site} onSiteChange={setSelectedSiteId} onNavigate={setView} />
          )}
          {site && view === 'rotation' && (
            <RotationPlannerScreen key={site.id} siteId={site.id} onCompared={() => setView('overview')} />
          )}
          {site && view === 'journey' && <DataJourneyScreen siteId={site.id} />}
          {site && view === 'evidence' && <EvidenceScreen siteId={site.id} />}
        </main>
      </div>
    </div>
  )
}

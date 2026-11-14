import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import pinIcon from '../assets/v2/icon-pin.svg'
import { StateView } from '../components/StateView'
import { Badge, Icon, type Tone } from '../components/ui'
import type { Site, SiteLoadStatus } from '../types/contracts'
import { AddFarmPanel } from './AddFarmPanel'

/**
 * My farms: the one place to list, add, open, rename, archive and restore the signed-in user's farms (D14).
 * No Figma frame: `.card`, `.btn` and `.badge` patterns of frame 25:49.
 */
export function FarmsScreen({
  currentSiteId,
  onOpen,
  onChange,
}: {
  currentSiteId: string | undefined
  onOpen: (siteId: string) => void
  /** Farms were added, renamed, archived or restored: the workspace's farm list must refresh. */
  onChange: () => void
}) {
  const [version, setVersion] = useState(0)
  const farms = useAsync(api.allSites, [version])
  const [adding, setAdding] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const [notice, setNotice] = useState('')

  // Keep the last list on screen while a refresh is in flight, so cards do not flash after every edit.
  const [list, setList] = useState<Site[] | null>(null)
  useEffect(() => {
    if (farms.status === 'ready') setList(farms.data)
  }, [farms])
  const all = list ?? []
  const active = all.filter((s) => !s.archived)
  const archived = all.filter((s) => s.archived)
  const shown = showArchived ? all : active
  const noFarms = list !== null && all.length === 0
  const refresh = () => {
    setVersion((v) => v + 1)
    onChange()
  }

  return (
    <>
      <div className="farms-heading">
        <div className="page-head">
          <h1 className="page-title" tabIndex={-1}>
            My farms
          </h1>
          <p className="muted">Your fields, their history and your saved decisions. Only you can see them.</p>
        </div>
        {!noFarms && !adding && (
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
            + Add a farm
          </button>
        )}
      </div>

      {notice && (
        <p className="account__ok" role="status">
          {notice}
        </p>
      )}

      {noFarms && (
        <div className="farms-empty">
          <span className="tile farms-empty__icon">
            <Icon src={pinIcon} size={20} />
          </span>
          <div>
            <strong>Add your first farm</strong>
            <span>Place it on the map below. We load its weather, soil and satellite history for you.</span>
          </div>
        </div>
      )}

      {(adding || noFarms) && (
        <AddFarmPanel
          onOpen={onOpen}
          onCreated={() => {
            // Keep the panel (and its load progress) open once the first farm appears in the list.
            setAdding(true)
            refresh()
          }}
          onClose={noFarms ? undefined : () => setAdding(false)}
        />
      )}

      {farms.status === 'loading' && list === null && <StateView kind="loading" title="Loading your farms…" />}
      {farms.status === 'error' && (
        <StateView kind="failed" title="Could not load your farms">
          {farms.error.message}{' '}
          <button type="button" className="link" onClick={() => setVersion((v) => v + 1)}>
            Try again
          </button>
        </StateView>
      )}

      {all.length > 0 && (
        <section className="farms-list-section" aria-labelledby="farms-list-h">
          <div className="farms-list-head">
            <h2 id="farms-list-h">
              {active.length} {active.length === 1 ? 'farm' : 'farms'}
              {archived.length > 0 && <span className="muted"> · {archived.length} archived</span>}
            </h2>
            {archived.length > 0 && (
              <label className="check-inline">
                <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
                Show archived
              </label>
            )}
          </div>
          {shown.length === 0 ? (
            <StateView kind="empty" title="All your farms are archived">
              Tick “Show archived” to restore one, or add a new farm.
            </StateView>
          ) : (
            <div className="farm-grid">
              {shown.map((site) => (
                <FarmCard
                  key={site.id}
                  site={site}
                  current={site.id === currentSiteId}
                  onOpen={() => onOpen(site.id)}
                  onSaved={(text) => {
                    setNotice(text)
                    refresh()
                  }}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </>
  )
}

function loadBadge(load: SiteLoadStatus | null, archived: boolean): { tone: Tone; label: string } {
  if (archived) return { tone: 'neutral', label: 'Archived' }
  if (!load) return { tone: 'neutral', label: 'Checking…' }
  if (load.status === 'queued' || load.status === 'running') return { tone: 'info', label: 'Loading data…' }
  if (load.status === 'failed') return { tone: 'warning', label: 'Load failed' }
  return load.has_strategies ? { tone: 'success', label: 'Ready to compare' } : { tone: 'success', label: 'Observe only' }
}

function FarmCard({
  site,
  current,
  onOpen,
  onSaved,
}: {
  site: Site
  current: boolean
  onOpen: () => void
  onSaved: (notice: string) => void
}) {
  const [load, setLoad] = useState<SiteLoadStatus | null>(null)
  const [renaming, setRenaming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Load progress per farm; polled while its data is still loading.
  useEffect(() => {
    let active = true
    let timer: number | undefined
    const poll = () =>
      api.siteLoad(site.id).then(
        (s) => {
          if (!active) return
          setLoad(s)
          if (s.status === 'queued' || s.status === 'running') timer = window.setTimeout(poll, 4000)
        },
        () => active && setLoad(null),
      )
    void poll()
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [site.id])

  const loading = load?.status === 'queued' || load?.status === 'running'
  const badge = loadBadge(load, !!site.archived)

  async function save(name: string, archived: boolean, notice: string) {
    setBusy(true)
    setError('')
    try {
      await api.updateSite(site.id, { name, archived })
      setRenaming(false)
      onSaved(notice)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update this farm.')
    } finally {
      setBusy(false)
    }
  }

  const rename = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get('name') ?? '')
    void save(name, !!site.archived, 'Farm renamed.')
  }

  return (
    <article className={`card farm-card ${site.archived ? 'farm-card--archived' : ''}`} aria-label={site.name}>
      <div className="farm-card__head">
        <span className="tile farm-card__icon" aria-hidden="true">
          {site.name.charAt(0).toUpperCase()}
        </span>
        <div className="farm-card__title">
          <h3>{site.name}</h3>
          <span className="small muted">
            {site.latitude.toFixed(4)}, {site.longitude.toFixed(4)}
            {site.area_ha != null && ` · ${site.area_ha} ha`}
          </span>
        </div>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>
      {current && !site.archived && <span className="small muted">Currently open in the workspace</span>}

      {renaming ? (
        <form className="form farm-card__rename" onSubmit={rename}>
          <label>
            Farm name
            <input type="text" name="name" defaultValue={site.name} required maxLength={120} autoFocus />
          </label>
          <div className="form__actions">
            <button type="button" className="btn btn--secondary" disabled={busy} onClick={() => setRenaming(false)}>
              Cancel
            </button>
            <button className="btn btn--primary" disabled={busy}>
              {busy ? 'Saving…' : 'Save name'}
            </button>
          </div>
        </form>
      ) : (
        <div className="farm-card__actions">
          {!site.archived && (
            <button
              type="button"
              className="btn btn--primary"
              disabled={loading}
              title={loading ? 'Its data is still loading' : undefined}
              onClick={onOpen}
            >
              Open farm
            </button>
          )}
          <button
            type="button"
            className="btn btn--secondary"
            disabled={busy || loading}
            title={loading ? 'Wait for the data load to finish' : undefined}
            onClick={() => setRenaming(true)}
          >
            Rename
          </button>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={busy || loading}
            title={loading ? 'Wait for the data load to finish' : undefined}
            onClick={() =>
              void save(
                site.name,
                !site.archived,
                site.archived ? 'Farm restored.' : 'Farm archived. Its data and decisions are kept.',
              )
            }
          >
            {busy ? 'Saving…' : site.archived ? 'Restore' : 'Archive'}
          </button>
        </div>
      )}
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}
    </article>
  )
}

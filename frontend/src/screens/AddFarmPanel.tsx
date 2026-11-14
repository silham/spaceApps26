import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { StateView } from '../components/StateView'
import { Badge } from '../components/ui'
import { OSM_ATTRIBUTION, OSM_STYLE, trackContainerSize } from '../journey/basemap'
import type { SiteLoadStatus } from '../types/contracts'

type Pos = [number, number] // [lon, lat]

function PickerMap({
  point,
  outline,
  onClick,
}: {
  point: Pos | null
  outline: Pos[]
  onClick: (p: Pos) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  // isStyleLoaded() is false whenever basemap tiles are still fetching, so readiness is tracked from 'load'.
  const [ready, setReady] = useState(false)
  const click = useRef(onClick)
  click.current = onClick

  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({ container: el.current, style: OSM_STYLE, center: [0, 20], zoom: 1.5 })
    const stopResize = trackContainerSize(m, el.current)
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    m.on('click', (e) => click.current([e.lngLat.lng, e.lngLat.lat]))
    m.on('load', () => {
      m.addSource('draw', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      m.addLayer({ id: 'fill', type: 'fill', source: 'draw', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#1e6b45', 'fill-opacity': 0.2 } })
      m.addLayer({ id: 'line', type: 'line', source: 'draw', filter: ['!=', ['geometry-type'], 'Point'], paint: { 'line-color': '#1e6b45', 'line-width': 2 } })
      m.addLayer({ id: 'pt', type: 'circle', source: 'draw', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': 6, 'circle-color': '#e59a0b', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } })
      setReady(true)
    })
    map.current = m
    return () => {
      stopResize()
      m.remove()
      map.current = null
      setReady(false)
    }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    const feats: unknown[] = []
    // While drawing, show the closed shape as soon as there are 3 corners so the field is visible before Finish.
    if (outline.length >= 3) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...outline, outline[0]]] } })
    else if (outline.length === 2) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: outline } })
    for (const v of outline) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: v } })
    if (point) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: point } })
    const src = m.getSource('draw') as maplibregl.GeoJSONSource | undefined
    src?.setData({ type: 'FeatureCollection', features: feats } as never)
  }, [point, outline, ready])

  return (
    <div
      ref={el}
      className="footmap__canvas"
      style={{ height: 460, cursor: 'crosshair' }}
      role="application"
      aria-label="World map: click to place your farm, or draw its field outline"
    />
  )
}

/**
 * Add a farm anywhere in the world (D13: observe only), shown inside My farms. Click the map to place the farm,
 * optionally draw the field outline, then load its data. No Figma frame: card, button and badge patterns of 25:49.
 */
export function AddFarmPanel({
  onOpen,
  onCreated,
  onClose,
}: {
  onOpen: (siteId: string) => void
  /** The farm row exists as soon as loading starts, and again when it finishes: refresh the list. */
  onCreated: () => void
  /** Absent when the user has no farms yet, so the panel cannot be dismissed. */
  onClose?: () => void
}) {
  const [name, setName] = useState('')
  const [point, setPoint] = useState<Pos | null>(null)
  const [outline, setOutline] = useState<Pos[]>([])
  const [drawing, setDrawing] = useState(false)
  const [job, setJob] = useState<SiteLoadStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const created = useRef(onCreated)
  created.current = onCreated
  const finished = job?.status === 'done' || job?.status === 'failed'
  useEffect(() => {
    if (finished) created.current()
  }, [finished])

  useEffect(() => {
    if (!job || job.status === 'done' || job.status === 'failed') return
    const t = window.setTimeout(() => {
      api.siteLoad(job.site_id).then(setJob, (e: Error) => setError(e.message))
    }, 3000)
    return () => window.clearTimeout(t)
  }, [job])

  const onMapClick = (p: Pos) => {
    if (drawing) setOutline((o) => [...o, p])
    else setPoint(p)
  }

  const submit = () => {
    if (!point) return
    setBusy(true)
    setError(null)
    api
      .createSite({
        name: name.trim(),
        latitude: point[1],
        longitude: point[0],
        boundary_geojson: outline.length >= 3 ? { type: 'Polygon', coordinates: [[...outline, outline[0]]] } : null,
      })
      .then((j) => {
        setJob(j)
        onCreated()
      }, (e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const canSubmit = Boolean(point) && name.trim() !== '' && !drawing && !busy && (!job || job.status === 'failed')
  const loading = job && (job.status === 'queued' || job.status === 'running')

  return (
    <>
      <section className="card page-card" aria-labelledby="add-h">
        <div className="card-head">
          <div className="card-title">
            <h2 id="add-h">Add a farm: where is your field?</h2>
          <p>
            Click the map to place your farm, then draw the field outline if you can. We load 45 years of NASA POWER weather, soil
            information and satellite greenness for that spot. This takes a minute or two.
          </p>
          </div>
          {onClose && (
            <button type="button" className="btn btn--secondary" onClick={onClose}>
              Close
            </button>
          )}
        </div>
        <StateView kind="unavailable" title="What happens next">
          Once the data has loaded you will see the field history, data quality and evidence for this location. To compare
          crops, open the Rotation planner, choose up to three rotations and run them on this farm's own weather and soil.
        </StateView>

        <div className="row">
          <button
            type="button"
            className={`btn ${drawing ? 'btn--primary' : 'btn--secondary'}`}
            aria-pressed={drawing}
            onClick={() => {
              if (drawing) setDrawing(false)
              else {
                setOutline([])
                setDrawing(true)
              }
            }}
          >
            {drawing ? (outline.length >= 3 ? 'Finish outline' : 'Cancel outline') : 'Draw field outline'}
          </button>
          {outline.length > 0 && !drawing && (
            <button type="button" className="btn btn--secondary" onClick={() => setOutline([])}>
              Clear outline
            </button>
          )}
          <span className="small muted">
            {drawing
              ? `Click each corner of the field (${outline.length} so far), then Finish.`
              : point
                ? `Farm point: ${point[1].toFixed(5)}, ${point[0].toFixed(5)}${outline.length >= 3 ? ` · outline with ${outline.length} corners` : ''}`
                : 'Click the map to place the farm.'}
          </span>
        </div>

        <ErrorBoundary what="The map">
          <PickerMap point={point} outline={outline} onClick={onMapClick} />
        </ErrorBoundary>
        <p className="small muted">Basemap {OSM_ATTRIBUTION}, for orientation only; it is not used in any calculation.</p>

        <div className="form" style={{ maxWidth: 520 }}>
          <label>
            Farm name
            <input type="text" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="e.g. North paddock" />
          </label>
          <div className="row">
            <label>
              Latitude
              <input
                type="number"
                step="0.00001"
                value={point ? point[1] : ''}
                onChange={(e) => setPoint([point?.[0] ?? 0, Number(e.target.value)])}
              />
            </label>
            <label>
              Longitude
              <input
                type="number"
                step="0.00001"
                value={point ? point[0] : ''}
                onChange={(e) => setPoint([Number(e.target.value), point?.[1] ?? 0])}
              />
            </label>
          </div>
          <div className="form__actions" style={{ justifyContent: 'flex-start' }}>
            <button type="button" className="btn btn--primary" disabled={!canSubmit} onClick={submit}>
              {busy ? 'Starting…' : 'Load this farm'}
            </button>
          </div>
        </div>
        {error && (
          <p className="run-error" role="alert">
            ⚠ {error}
          </p>
        )}
      </section>

      {job && (
        <section className="card page-card" aria-labelledby="load-h" aria-live="polite">
          <h2 id="load-h">Loading data for {name || job.site_id}</h2>
          <ul className="list">
            {job.steps.map((s) => (
              <li key={s.name}>
                <div className="row">
                  <strong>{s.source}</strong>
                  <Badge
                    tone={s.status === 'done' ? 'success' : s.status === 'failed' ? 'warning' : s.status === 'running' ? 'info' : 'neutral'}
                  >
                    {s.status === 'running' ? 'Loading…' : s.status === 'done' ? 'Loaded' : s.status === 'failed' ? 'Not loaded' : 'Waiting'}
                  </Badge>
                </div>
                {s.message && <span className="small">{s.message}</span>}
              </li>
            ))}
          </ul>
          {loading && <StateView kind="loading" title="Loading… you can keep this page open." />}
          {job.status === 'failed' && (
            <StateView kind="failed" title="The farm could not be loaded">
              Weather is needed for everything else. Check the message above and try again.
            </StateView>
          )}
          {job.status === 'done' && (
            <div className="row">
              <button type="button" className="btn btn--primary" onClick={() => onOpen(job.site_id)}>
                Open this farm
              </button>
              <span className="small muted">Anything marked "Not loaded" stays missing; it is never filled with a guess.</span>
            </div>
          )}
        </section>
      )}
    </>
  )
}

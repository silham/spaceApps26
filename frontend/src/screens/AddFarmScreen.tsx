import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { StateView } from '../components/StateView'
import { Badge } from '../components/ui'
import type { SiteLoadStatus } from '../types/contracts'

type Pos = [number, number] // [lon, lat]

const OSM_ATTRIBUTION = '© OpenStreetMap contributors (ODbL)'
// Basemap for orientation only: it is never used in a calculation (rule 2; docs/decisions.md D13).
const STYLE = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution: OSM_ATTRIBUTION,
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
} as const

function PickerMap({
  point,
  outline,
  drawing,
  onClick,
}: {
  point: Pos | null
  outline: Pos[]
  drawing: boolean
  onClick: (p: Pos) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const click = useRef(onClick)
  click.current = onClick

  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({ container: el.current, style: STYLE as never, center: [0, 20], zoom: 1.5 })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    m.on('click', (e) => click.current([e.lngLat.lng, e.lngLat.lat]))
    m.on('load', () => {
      m.addSource('draw', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      m.addLayer({ id: 'fill', type: 'fill', source: 'draw', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#1e6b45', 'fill-opacity': 0.2 } })
      m.addLayer({ id: 'line', type: 'line', source: 'draw', filter: ['!=', ['geometry-type'], 'Point'], paint: { 'line-color': '#1e6b45', 'line-width': 2 } })
      m.addLayer({ id: 'pt', type: 'circle', source: 'draw', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': 6, 'circle-color': '#e59a0b', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } })
    })
    map.current = m
    return () => {
      m.remove()
      map.current = null
    }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m) return
    const draw = () => {
      const feats: unknown[] = []
      if (outline.length >= 3 && !drawing)
        feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...outline, outline[0]]] } })
      else if (outline.length >= 2) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: outline } })
      for (const v of outline) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: v } })
      if (point) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: point } })
      const src = m.getSource('draw') as maplibregl.GeoJSONSource | undefined
      src?.setData({ type: 'FeatureCollection', features: feats } as never)
    }
    if (m.isStyleLoaded()) draw()
    else m.once('load', draw)
  }, [point, outline, drawing])

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
 * Add a farm anywhere in the world (D13: observe only). Click the map to place the farm, optionally draw
 * the field outline, then load its data. No Figma frame: card, button and badge patterns of frame 25:49.
 */
export function AddFarmScreen({ onOpen }: { onOpen: (siteId: string) => void }) {
  const [name, setName] = useState('')
  const [point, setPoint] = useState<Pos | null>(null)
  const [outline, setOutline] = useState<Pos[]>([])
  const [drawing, setDrawing] = useState(false)
  const [job, setJob] = useState<SiteLoadStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

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
      .then(setJob, (e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const canSubmit = Boolean(point) && name.trim() !== '' && !drawing && !busy && (!job || job.status === 'failed')
  const loading = job && (job.status === 'queued' || job.status === 'running')

  return (
    <>
      <h1 className="page-title" tabIndex={-1}>
        Add a farm
      </h1>
      <section className="card page-card" aria-labelledby="add-h">
        <div className="card-title">
          <h2 id="add-h">Where is your field?</h2>
          <p>
            Click the map to place your farm, then draw the field outline if you can. We load 45 years of NASA POWER weather, soil
            information and satellite greenness for that spot. This takes a minute or two.
          </p>
        </div>
        <StateView kind="unavailable" title="Observe only for new farms">
          You will see the field history, data quality and evidence for any location. Comparing rotations needs locally reviewed
          strategies and crop calendars, which exist only for the preset Kansas field so far.
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
          <PickerMap point={point} outline={outline} drawing={drawing} onClick={onMapClick} />
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

import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { FootprintFeature } from './payloads'

/** Legend entries by `properties.layer`. Wording follows docs/limitations.md. */
const LAYERS: Record<string, { name: string; color: string; note: string }> = {
  field_boundary: { name: 'Field boundary (approximate)', color: '#1e6b45', note: 'from a 30 m crop map' },
  source_footprint: { name: 'Satellite pixel (MODIS)', color: '#2f7fd8', note: 'the sensor’s real pixel shape' },
  weather_grid_point: { name: 'Weather grid point (NASA POWER)', color: '#e59a0b', note: 'one cell is roughly 50 km across' },
}

type Pos = [number, number]
function walk(c: unknown, out: Pos[]): void {
  if (Array.isArray(c) && typeof c[0] === 'number') out.push([c[0], c[1] as number])
  else if (Array.isArray(c)) c.forEach((x) => walk(x, out))
}
function boundsOf(features: FootprintFeature[]): [Pos, Pos] | null {
  const pts: Pos[] = []
  features.forEach((f) => walk(f.geometry.coordinates, pts))
  if (pts.length === 0) return null
  const xs = pts.map((p) => p[0])
  const ys = pts.map((p) => p[1])
  return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]]
}

/**
 * Align card map: native footprints only, on a plain background. There is deliberately no imagery
 * basemap, so the map adds no unlisted data source and shows only what the pipeline used.
 * The weather grid point lies far outside the field, so it is off by default ("wider view").
 */
export function FootprintMap({ features }: { features: FootprintFeature[] }) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const hasGrid = features.some((f) => f.layer === 'weather_grid_point')
  // With no outline or pixel to zoom to, the grid point is all there is, so show it rather than an empty map.
  const [wide, setWide] = useState(() => !features.some((f) => f.layer !== 'weather_grid_point'))
  const shown = useMemo(() => features.filter((f) => wide || f.layer !== 'weather_grid_point'), [features, wide])

  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({
      container: el.current,
      style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#eef1ef' } }] },
      attributionControl: false,
      interactive: true,
      center: [0, 0],
      zoom: 1,
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
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
      for (const id of ['fill', 'line', 'point']) if (m.getLayer(id)) m.removeLayer(id)
      if (m.getSource('fp')) m.removeSource('fp')
      m.addSource('fp', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: shown.map((f) => ({ type: 'Feature', geometry: f.geometry, properties: { layer: f.layer } })) } as never,
      })
      const color = ['match', ['get', 'layer'], ...Object.entries(LAYERS).flatMap(([k, v]) => [k, v.color]), '#85938b'] as never
      m.addLayer({ id: 'fill', type: 'fill', source: 'fp', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': color, 'fill-opacity': 0.18 } })
      m.addLayer({ id: 'line', type: 'line', source: 'fp', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'line-color': color, 'line-width': 2 } })
      m.addLayer({ id: 'point', type: 'circle', source: 'fp', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-color': color, 'circle-radius': 7, 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } })
      const b = boundsOf(shown)
      if (b) m.fitBounds(b, { padding: 48, maxZoom: 17, duration: 0 })
    }
    if (m.isStyleLoaded()) draw()
    else m.once('load', draw)
  }, [shown])

  const present = Object.entries(LAYERS).filter(([k]) => shown.some((f) => f.layer === k))
  return (
    <div className="footmap">
      <div ref={el} className="footmap__canvas" role="img" aria-label="Map of the field boundary, satellite pixel and weather grid point" />
      <div className="row footmap__bar">
        {hasGrid && (
          <button type="button" className="btn btn--secondary" aria-pressed={wide} onClick={() => setWide((w) => !w)}>
            {wide ? 'Zoom to field and satellite pixel' : 'Show weather grid point (wider view)'}
          </button>
        )}
      </div>
      <ul className="footmap__legend small">
        {present.map(([k, v]) => (
          <li key={k}>
            <i style={{ background: v.color }} />
            <strong>{v.name}</strong> <span className="muted">· {v.note}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

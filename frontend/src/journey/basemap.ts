import type maplibregl from 'maplibre-gl'

export const OSM_ATTRIBUTION = '© OpenStreetMap contributors (ODbL)'

/** Basemap for orientation only: it is never used in a calculation (rule 2; docs/decisions.md D13). */
export const OSM_STYLE: maplibregl.StyleSpecification = {
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
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#eef1ef' } },
    { id: 'osm', type: 'raster', source: 'osm' },
  ],
}

/** Keep the canvas sized to its container (it can mount hidden or change width with the layout). */
export function trackContainerSize(m: maplibregl.Map, el: HTMLElement): () => void {
  const ro = new ResizeObserver(() => m.resize())
  ro.observe(el)
  return () => ro.disconnect()
}

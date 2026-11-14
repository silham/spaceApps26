import farmland from '../../assets/farmland.png'
import fieldBoundary from '../../assets/v2/field-boundary.svg'
import layersIcon from '../../assets/v2/icon-layers.svg'
import pinIcon from '../../assets/v2/icon-pin.svg'
import mapGrid from '../../assets/v2/map-grid.svg'
import { Badge, Icon } from '../../components/ui'

const LAYER_REASON = 'Not available on the illustrative map'

/**
 * Illustrative field map (Figma node 26:158): static imagery with the MODIS pixel grid and field
 * boundary. Layer switching needs the live map, so the other two layers are disabled with a reason.
 */
export function FieldMap({ fieldLabel, onViewSource }: { fieldLabel: string; onViewSource: () => void }) {
  return (
    <section className="map" aria-label="Field map (illustrative)">
      <img className="map__imagery" src={farmland} alt="Illustrative farmland imagery" />
      <img className="map__grid" src={mapGrid} alt="" />
      <div className="map__field">
        <img src={fieldBoundary} alt="" />
      </div>
      <div className="map__scrim" />
      <div className="map__float map__layers" role="group" aria-label="Map layers">
        <Icon src={layersIcon} size={16} />
        <button type="button" className="map__layer" aria-pressed="true">
          Satellite
        </button>
        <button type="button" className="map__layer" aria-pressed="false" aria-disabled="true" title={LAYER_REASON}>
          Vegetation
        </button>
        <button type="button" className="map__layer" aria-pressed="false" aria-disabled="true" title={LAYER_REASON}>
          Data footprints
        </button>
      </div>
      <Badge tone="neutral" className="map__float map__badge">
        Illustrative map
      </Badge>
      <Badge tone="info" className="map__float map__footprint">
        MODIS footprint · nominal 250 m
      </Badge>
      <div className="map__float map__name">
        <Icon src={pinIcon} size={14} />
        {fieldLabel}
      </div>
      <div className="map__float map__panel map__pixel">
        <strong>MODIS: mixed-pixel context</strong>
        <span>Nominal 250 m (~5.4 ha)</span>
        <button type="button" className="link" onClick={onViewSource}>
          View source and scale ↗
        </button>
      </div>
      <div className="map__float map__panel map__legend">
        <span>
          <i />
          Field boundary
        </span>
        <span>
          <i />
          MODIS pixel 250 m
        </span>
      </div>
    </section>
  )
}

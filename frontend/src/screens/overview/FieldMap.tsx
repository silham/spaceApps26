import farmland from '../../assets/farmland.png'
import mapOverlay from '../../assets/map-overlay.svg'
import { ctl } from '../../components/ctl'

const LAYER_REASON = 'Not available on the illustrative map'

/**
 * Illustrative field map (Figma node 3:99): static imagery with the field boundary and MODIS pixel
 * overlay. Layer switching needs the live map, so the other two layers are disabled with a reason.
 */
export function FieldMap({ fieldLabel, onViewSource }: { fieldLabel: string; onViewSource: () => void }) {
  return (
    <section className="map" aria-label="Field map (illustrative)">
      <img className="map__imagery" src={farmland} alt="Illustrative farmland imagery" />
      <img className="map__overlay" src={mapOverlay} alt="" />
      <div className="map__layers" role="group" aria-label="Map layers">
        <button type="button" className={ctl('primary')} aria-pressed="true">
          Satellite
        </button>
        <button type="button" className={ctl('outline')} aria-pressed="false" aria-disabled="true" title={LAYER_REASON}>
          Vegetation
        </button>
        <button type="button" className={ctl('outline')} aria-pressed="false" aria-disabled="true" title={LAYER_REASON}>
          Data footprints
        </button>
      </div>
      <span className={ctl('evidence', 'map__footprint')}>MODIS footprint · nominal 250 m</span>
      <span className={ctl('outline', 'map__field')}>{fieldLabel}</span>
      <span className={ctl('neutral', 'map__badge')}>Illustrative map</span>
      <div className="map__panel map__pixel">
        <strong>MODIS: mixed-pixel context</strong>
        <span className="small">Nominal 250 m (~5.4 ha)</span>
        <button type="button" className="link" onClick={onViewSource}>
          View source and scale ↗
        </button>
      </div>
      <div className="map__panel map__legend">
        <span>▢  Field boundary</span>
        <span>▧  MODIS pixel    250 m</span>
      </div>
    </section>
  )
}

import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { AsyncView } from '../components/AsyncView'
import { DemoBadge } from '../components/DemoBadge'
import { SourceLabel } from '../components/SourceLabel'

/** Observe: farm map, evidence layers, environmental timeline, farmer inputs. TODO(M2): build per Figma. */
export function ObserveScreen() {
  const sites = useAsync(api.sites, [])
  const sources = useAsync(api.sources, [])
  return (
    <section aria-labelledby="observe-h">
      <h2 id="observe-h">Observe</h2>
      <AsyncView state={sites} isEmpty={(d) => d.length === 0}>
        {(data) =>
          data.map((site) => (
            <article key={site.id}>
              <h3>
                {site.name} {site.is_demo && <DemoBadge />}
              </h3>
              <p>
                {site.latitude.toFixed(3)}, {site.longitude.toFixed(3)} · {site.timezone}
              </p>
              {/* TODO(M2): MapLibre map with boundary + native data footprints, static fallback image */}
            </article>
          ))
        }
      </AsyncView>
      <AsyncView state={sources}>{(data) => <SourceLabel sources={data} />}</AsyncView>
    </section>
  )
}

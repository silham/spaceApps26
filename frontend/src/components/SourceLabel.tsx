import type { Source } from '../types/contracts'

/**
 * Short source label + expandable details. Required beside every chart, map layer, metric and export
 * (AGENTS.md rule 2). TODO(M2): restyle to match Figma.
 */
export function SourceLabel({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return <small>Source: none recorded</small>
  return (
    <details>
      <summary>
        <small>Source: {sources.map((s) => `${s.provider} ${s.product}`).join(' · ')}</small>
      </summary>
      <ul>
        {sources.map((s) => (
          <li key={s.id}>
            <strong>{s.provider}</strong>, {s.product}
            {s.version ? ` (${s.version})` : ''} · kind: {s.kind}
            {s.spatial_resolution ? ` · ${s.spatial_resolution}` : ''}
            {s.temporal_resolution ? ` / ${s.temporal_resolution}` : ''}
            {s.coverage_start ? ` · ${s.coverage_start} to ${s.coverage_end ?? '?'}` : ''}
            {s.license ? ` · license: ${s.license}` : ''}
            {s.url ? (
              <>
                {' · '}
                <a href={s.url} target="_blank" rel="noreferrer">link</a>
              </>
            ) : null}
            {s.limitations ? <div>Limitations: {s.limitations}</div> : null}
          </li>
        ))}
      </ul>
    </details>
  )
}

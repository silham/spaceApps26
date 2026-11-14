import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { AsyncView } from '../components/AsyncView'
import { DemoBadge } from '../components/DemoBadge'
import { RangeBar } from '../components/RangeBar'
import { SourceLabel } from '../components/SourceLabel'
import { StateView } from '../components/StateView'
import { SelectControl } from '../components/ui'
import { METRICS } from '../live/model'
import type { ParamValue } from '../types/contracts'

const pv = (p: ParamValue | undefined) =>
  p == null || p.value == null ? <em>missing: blocks the claim</em> : <>{p.value} {p.unit}</>

/**
 * Evidence & validation: the source register, the run's stored results and limitations, the crop
 * parameters with their citations, and stored validation results. No Figma frame exists for this
 * view; it reuses the dashboard's card pattern.
 */
export function EvidenceScreen({ siteId }: { siteId: string | undefined }) {
  const [picked, setPicked] = useState<string | null>(null)
  const runs = useAsync(() => (siteId ? api.runs(siteId) : Promise.resolve([])), [siteId])
  const list = runs.status === 'ready' ? runs.data : []
  const runId = picked ?? list[0]?.run.id
  const run = list.find((r) => r.run.id === runId)
  const sources = useAsync(api.sources, [])
  const results = useAsync(() => (runId ? api.results(runId) : Promise.resolve([])), [runId])
  const crops = useAsync(api.crops, [])
  const validations = useAsync(() => (siteId ? api.validations(siteId) : Promise.resolve([])), [siteId])
  const used = new Set(run?.source_ids ?? [])
  const limitations = run?.limitations ?? []
  const unsupported = run?.unsupported_claims ?? []

  return (
    <>
      <h1 className="page-title" tabIndex={-1}>Evidence &amp; validation</h1>

      <section className="card page-card" aria-labelledby="sources-h">
        <h2 id="sources-h">Sources used</h2>
        <p className="small muted">
          {run ? `Only the sources run ${run.run.id} actually used are marked below.` : 'All registered sources.'} Observations, reanalysis, modelled maps,
          farmer inputs, literature values and simulated outputs are kept apart (the kind is shown per source).
        </p>
        <AsyncView state={sources}>
          {(data) => <SourceLabel sources={run ? data.filter((s) => used.has(s.id)) : data} />}
        </AsyncView>
      </section>

      <section className="card page-card" aria-labelledby="results-h">
        <div className="row">
          <h2 id="results-h">Results</h2>
          {list.length > 1 && (
            <SelectControl
              label="Run"
              value={runId ?? ''}
              options={list.map((r) => ({ value: r.run.id, label: `${r.run.id} · ${r.run.created_at.slice(0, 16).replace('T', ' ')}` }))}
              onChange={setPicked}
            />
          )}
          {run?.run.is_demo && <DemoBadge />}
        </div>
        {runs.status === 'ready' && list.length === 0 && (
          <StateView kind="empty" title="No comparison run yet">Run the comparison from the Overview to see results here.</StateView>
        )}
        {run && (
          <p className="small muted">
            Run {run.run.id} · model {run.run.model_version} · {run.run.n_paths} paths · {run.run.resampling_method} · seed {run.run.seed} · weather source{' '}
            {run.run.weather_source_id}
          </p>
        )}
        <AsyncView state={results} isEmpty={() => false}>
          {(data) =>
            data.length === 0 ? null : (
              <ul className="list">
                {data.map((r) => (
                  <li key={r.id}>
                    <div className="row">
                      <span>
                        {run?.strategies.find((s) => s.id === r.strategy_id)?.name.split(':')[0] ?? r.strategy_id} · {METRICS[r.metric]?.label ?? r.metric}: <RangeBar result={r} />
                      </span>
                      {r.is_demo && <DemoBadge />}
                    </div>
                    <span className="small muted">Sources: {r.source_ids.join(', ') || 'none recorded'}</span>
                  </li>
                ))}
              </ul>
            )
          }
        </AsyncView>
        {limitations.length > 0 && (
          <details>
            <summary>Limitations of this run ({limitations.length})</summary>
            <ul className="list list--tight small">{limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </details>
        )}
        {unsupported.length > 0 && (
          <p className="small muted">Not estimated by this tool: {unsupported.join('; ')}.</p>
        )}
      </section>

      <section className="card page-card" aria-labelledby="crops-h">
        <h2 id="crops-h">Crop parameters</h2>
        <p className="small muted">Each value carries its reference. A missing value blocks any claim that needs it; it is never guessed.</p>
        <AsyncView state={crops} isEmpty={(d) => d.length === 0}>
          {(data) => (
            <div className="table-wrap">
              <table className="metrics-table">
                <thead>
                  <tr><th scope="col">Crop</th><th scope="col">Kc mid</th><th scope="col">Stage lengths (days)</th><th scope="col">Root depth</th><th scope="col">p</th><th scope="col">References</th></tr>
                </thead>
                <tbody>
                  {data.map((c) => (
                    <tr key={c.id}>
                      <th scope="row">{c.name}{c.is_demo && <> <DemoBadge /></>}</th>
                      <td>{pv(c.kc_mid)}</td>
                      <td>{Object.entries(c.stage_lengths_days).map(([k, v]) => `${k} ${v.value ?? '?'}`).join(' · ')}</td>
                      <td>{pv(c.max_root_depth_m)}</td>
                      <td>{pv(c.depletion_fraction_p)}</td>
                      <td className="small muted">{[c.kc_mid.reference, c.stage_lengths_days.ini?.reference].filter(Boolean).join(' · ') || 'none recorded'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncView>
      </section>

      <section className="card page-card" aria-labelledby="validation-h">
        <h2 id="validation-h">Validation</h2>
        <p className="small">
          Ranges are a central 80% simulation range (p10–p90), not a prediction interval. Whether they cover real outcomes has not been evaluated unless a
          result below says so.
        </p>
        <AsyncView state={validations} isEmpty={(d) => d.length === 0}>
          {(data) => (
            <ul className="list">
              {data.map((v) => (
                <li key={v.id}>
                  <strong>{v.target}</strong>
                  <span className="small">Reference: {v.reference}</span>
                  <span className="small muted">
                    n = {v.sample_count}
                    {v.train_period ? ` · train ${v.train_period.join(' to ')}` : ''}
                    {v.test_period ? ` · test ${v.test_period.join(' to ')}` : ''} · sources {v.source_ids?.join(', ') || 'none recorded'}
                  </span>
                  {v.failures && v.failures.length > 0 && <span className="small">Failures: {v.failures.join('; ')}</span>}
                  <span className="small muted">Independence: {v.independence_notes}</span>
                </li>
              ))}
            </ul>
          )}
        </AsyncView>
      </section>
    </>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import { useAsync } from '../../api/useAsync'
import alertIcon from '../../assets/v2/icon-alert-20.svg'
import branchIcon from '../../assets/v2/icon-branch.svg'
import calendarIcon from '../../assets/v2/icon-calendar.svg'
import clockIcon from '../../assets/v2/icon-clock.svg'
import infoIcon from '../../assets/v2/icon-info-18.svg'
import playIcon from '../../assets/v2/icon-play.svg'
import { DemoBadge } from '../../components/DemoBadge'
import { ErrorBoundary } from '../../components/ErrorBoundary'
import { StateView } from '../../components/StateView'
import { Icon, SelectControl } from '../../components/ui'
import type { StrategyView } from '../../demo/figmaDemo'
import { FootprintMap } from '../../journey/FootprintMap'
import { readFootprints } from '../../journey/payloads'
import type { View } from '../../layout/Sidebar'
import {
  METRICS,
  TONES,
  axisFor,
  changesSince,
  draftFromRequest,
  draftProblem,
  isFeasible,
  metricView,
  rankStrategies,
  requestFromDraft,
  resultFor,
  type Draft,
  type Priorities,
} from '../../live/model'
import type { FarmerContext, PairedDelta, Result, RunDetail, Site, SimulationMode } from '../../types/contracts'
import { FarmDetailsDialog } from './FarmDetailsDialog'
import { JourneySummary } from './JourneySummary'
import { NextStep } from './NextStep'
import { LivePrioritiesPanel } from './PrioritiesPanel'
import { LiveRotation } from './LiveRotation'
import { RunComparison } from './RunComparison'
import { TimelineCard } from './TimelineCard'
import { HarvestTable } from './HarvestTable'
import { TradeOffs } from './TradeOffs'

type RunState = { status: 'idle' } | { status: 'running' } | { status: 'failed'; message: string }

const joinList = (items: string[]) =>
  items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const fmt = (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toLocaleString('en-GB'))
const shortName = (name: string) => name.split(':')[0] ?? name
const OBSERVE_ONLY = 'Observe only: this farm has no rotations yet. Choose crops in the Rotation planner to compare them here.'

/**
 * Overview for a loaded farm: every number comes from the API (runs, results, paired deltas, replay,
 * journey, timeline, farmer inputs). Layout follows Figma frame 25:49; sections without a frame
 * (timeline, trade-offs, farm form) extend its card patterns (docs/decisions.md, UI assumptions).
 */
export function LiveOverview({
  sites,
  site,
  onSiteChange,
  onNavigate,
}: {
  sites: Site[]
  site: Site
  onSiteChange: (siteId: string) => void
  onNavigate: (view: View) => void
}) {
  const siteId = site.id
  const [reload, setReload] = useState(0)
  const runs = useAsync(() => api.runs(siteId), [siteId, reload])
  const journey = useAsync(() => api.journey(siteId), [siteId, reload])
  const crops = useAsync(api.crops, [])
  const rotationCrops = useAsync(api.rotationCrops, [])
  const storedRotations = useAsync(() => api.strategies(siteId), [siteId, reload])
  const sources = useAsync(api.sources, [reload])
  const timeline = useAsync(() => api.timeline(siteId), [siteId])
  const load = useAsync(() => api.siteLoad(siteId), [siteId])
  // Observe-only farm (D13): no locally reviewed strategies, so no comparison can be run.
  const observeOnly = load.status === 'ready' && !load.data.has_strategies
  const [farmer, setFarmer] = useState<FarmerContext | null>(null)
  useEffect(() => {
    api.farmerContext(siteId).then(setFarmer, () => setFarmer(null))
  }, [siteId])

  const [run, setRun] = useState<RunDetail | null>(null)
  const [results, setResults] = useState<Result[]>([])
  const [deltas, setDeltas] = useState<PairedDelta[]>([])
  const [draft, setDraft] = useState<Draft>(draftFromRequest(undefined))
  const [priorities, setPriorities] = useState<Priorities>({ conserveWater: 50, protectSoil: 50 })
  const [runState, setRunState] = useState<RunState>({ status: 'idle' })
  const [showRanges, setShowRanges] = useState(true)
  const [farmOpen, setFarmOpen] = useState(false)

  // Show the newest stored run when the farm changes (or the list first loads).
  const latest = runs.status === 'ready' ? (runs.data[0] ?? null) : null
  useEffect(() => {
    if (runs.status !== 'ready') return
    if (!run || run.run.site_id !== siteId) {
      setRun(latest)
      setDraft(draftFromRequest(latest?.request, farmer))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs.status, latest?.run.id, siteId])

  useEffect(() => {
    if (!run) {
      setResults([])
      setDeltas([])
      return
    }
    let cancelled = false
    Promise.all([api.results(run.run.id), api.deltas(run.run.id)]).then(
      ([r, d]) => {
        if (cancelled) return
        setResults(r)
        setDeltas(d)
      },
      (e: Error) => !cancelled && setRunState({ status: 'failed', message: `results could not be loaded: ${e.message}` }),
    )
    return () => {
      cancelled = true
    }
  }, [run])

  const names = Object.fromEntries((run?.strategies ?? []).map((s) => [s.id, shortName(s.name)]))
  const farmerChanged = Boolean(run && farmer?.updated_at && farmer.updated_at > run.run.created_at)
  // Rotations saved after the shown run (a different set of strategies): its results describe the old ones.
  const rotationsChanged = Boolean(
    run &&
      storedRotations.status === 'ready' &&
      storedRotations.data.length > 0 &&
      storedRotations.data.map((s) => s.id).sort().join() !== run.strategies.map((s) => s.id).sort().join(),
  )
  const changes = [...changesSince(run, draft, names, farmerChanged), ...(rotationsChanged ? ['rotations'] : [])]
  const outdated = changes.length > 0
  const problem = draftProblem(draft)
  const cropMap = useMemo(() => new Map((crops.status === 'ready' ? crops.data : []).map((c) => [c.id, c])), [crops])

  const runComparison = () => {
    if (problem) return
    setRunState({ status: 'running' })
    api.createRun(requestFromDraft(siteId, draft)).then(
      (detail) => {
        setRun(detail)
        setDraft(draftFromRequest(detail.request, farmer))
        setRunState({ status: 'idle' })
        setReload((n) => n + 1)
      },
      (e: Error) => setRunState({ status: 'failed', message: e.message }),
    )
  }

  const statuses = journey.status === 'ready' ? journey.data.map((s) => [s.stage, s.status] as const) : []
  const align = journey.status === 'ready' ? journey.data.find((s) => s.stage === 'align') : undefined
  const footprints = align ? readFootprints(align) : null
  const sourceById = new Map((sources.status === 'ready' ? sources.data : []).map((s) => [s.id, s]))
  const runSources = (run?.source_ids ?? []).map((id) => sourceById.get(id)).filter(Boolean)
  const soilSource = runSources.find((s) => s?.provider.includes('Soil') || s?.product.includes('SSURGO') || s?.product.includes('Soil'))
  const strategies = run?.strategies ?? []
  const ranking = rankStrategies(strategies, results, priorities)

  const views: StrategyView[] = strategies.map((s, i) => ({
    id: s.id,
    name: shortName(s.name),
    tone: TONES[i] ?? 'baseline',
    cells: [],
    waterStress: metricView(results, deltas, s.id, 'water_stress_days'),
    soilCover: metricView(results, deltas, s.id, 'cover_days'),
  }))
  const infeasible = Object.fromEntries(strategies.filter((s) => !isFeasible(s)).map((s) => [s.id, s.feasibility?.reasons ?? []]))
  const yearOf = (v: unknown) => Number(String(v).slice(0, 4))
  const sampleStart = run ? yearOf(run.run.sample_period[0]) : 0
  const sampleEnd = run ? yearOf(run.run.sample_period[1]) : 0
  const heldOut = run?.run.input_versions?.held_out_or_outside_pool_years

  const farmOptions = sites.map((s) => ({ value: s.id, label: `${s.name}${s.is_demo ? ' (DEMO)' : ''}` }))
  const lockReason = observeOnly
    ? 'No rotations yet: build them in the Rotation planner first.'
    : !run
      ? 'Run the comparison first.'
      : runState.status === 'running'
      ? 'Comparison is running…'
      : undefined

  return (
    <>
      <div className="header">
        <div className="header__title">
          <h1 tabIndex={-1}>Your farm. Different futures.</h1>
          <div className="header__subtitle">
            {(site.is_demo || run?.run.is_demo) && <DemoBadge />}
            <span>Compare rotations under the same historical weather.</span>
          </div>
        </div>
        <div className="header__controls">
          <SelectControl label="Farm" value={siteId} options={farmOptions} onChange={onSiteChange} />
          <button
            type="button"
            className="btn btn--primary"
            disabled={runState.status === 'running' || Boolean(problem) || observeOnly}
            title={observeOnly ? OBSERVE_ONLY : (problem ?? undefined)}
            onClick={runComparison}
          >
            <Icon src={playIcon} size={14} />
            {runState.status === 'running' ? 'Running…' : 'Run comparison'}
          </button>
        </div>
      </div>

      {run && outdated && (
        <div className="banner" role="status">
          <span className="tile">
            <Icon src={alertIcon} size={20} />
          </span>
          <div className="banner__text">
            <strong>Results outdated</strong>
            <span>{capitalise(joinList(changes))} changed. Run comparison to refresh.</span>
          </div>
          <span className="banner__run">Shown run {run.run.id}</span>
          <button type="button" className="btn btn--secondary" disabled={runState.status === 'running' || Boolean(problem)} onClick={runComparison}>
            Refresh results
          </button>
        </div>
      )}
      {problem && <p className="run-error" role="alert">⚠ {problem}</p>}
      {runState.status === 'running' && (
        <StateView kind="loading" title="Running the comparison…">
          Every strategy is simulated on the same {fmt(200)} resampled weather paths. This takes a few seconds.
        </StateView>
      )}
      {runState.status === 'failed' && (
        <p className="run-error" role="alert">
          ⚠ Comparison did not run: {runState.message}. The results below are unchanged.
        </p>
      )}

      {run && (
        <div className="stats">
          <div className="stat">
            <span className="tile tile--leaf">
              <Icon src={calendarIcon} size={20} />
            </span>
            <div className="stat__text">
              <strong>
                {sampleStart}–{sampleEnd}
              </strong>
              <span>Weather sampling window</span>
            </div>
          </div>
          <div className="stat">
            <span className="tile tile--info">
              <Icon src={branchIcon} size={20} />
            </span>
            <div className="stat__text">
              <strong>{run.run.n_paths}</strong>
              <span>Paired weather paths</span>
            </div>
          </div>
          <div className="stat">
            <span className="tile tile--violet">
              <Icon src={clockIcon} size={20} />
            </span>
            <div className="stat__text">
              <strong>{run.run.horizon_years} years</strong>
              <span>Simulation horizon</span>
            </div>
          </div>
          <div className="stat stat--note">
            <Icon src={infoIcon} size={18} />
            {heldOut && heldOut !== 'none' ? `${heldOut.split(',').length} years outside the sample pool (replay only)` : 'All loaded years are in the sample pool'}
            {run.excluded_blocks?.length ? ` · ${run.excluded_blocks.length} year(s) excluded for missing data` : ''}
          </div>
        </div>
      )}

      {statuses.length > 0 && <JourneySummary statuses={statuses as never} illustrative={false} onInspect={() => onNavigate('journey')} />}
      {journey.status === 'error' && <StateView kind="failed" title="Pipeline status could not be loaded">{journey.error.message}</StateView>}

      <div className="field-row">
        <section className="card page-card live-map" aria-labelledby="map-h">
          <div className="card-title card-title--small">
            <h2 id="map-h">{site.name}</h2>
            <p>
              {site.area_ha ? `${site.area_ha} ha · ` : ''}
              Field boundary and the native footprint of each data source (nothing resampled).
            </p>
          </div>
          {footprints && footprints.length > 0 ? (
            <ErrorBoundary what="The map">
              <FootprintMap features={footprints} />
            </ErrorBoundary>
          ) : (
            <StateView kind="unavailable">No mapped boundary or source footprints are stored for this farm.</StateView>
          )}
          <button type="button" className="link" onClick={() => onNavigate('evidence')}>
            View sources and scale ↗
          </button>
        </section>
        <LivePrioritiesPanel
          priorities={priorities}
          onPriorities={setPriorities}
          mode={draft.mode}
          onMode={(mode: SimulationMode) =>
            setDraft((d) => ({ ...d, mode, allocationMm: mode === 'fixed_allocation' ? (d.allocationMm ?? farmer?.irrigation_allocation_mm ?? null) : d.allocationMm }))
          }
          allocationMm={draft.allocationMm}
          onAllocation={(allocationMm) => setDraft((d) => ({ ...d, allocationMm }))}
          allocationChanged={changes.includes('irrigation limit')}
          soilLabel={
            soilSource
              ? `${soilSource.product}${farmer?.soil_confirmed ? ' · confirmed by farmer' : ' · not yet confirmed'}`
              : 'Stored soil profile'
          }
          equipmentLabel={farmer?.equipment?.length ? farmer.equipment.join(', ') : 'Not confirmed'}
          cropsLabel={
            farmer?.available_crop_ids
              ? farmer.available_crop_ids.map((c) => cropMap.get(c)?.name ?? c).join(', ') || 'None'
              : 'All catalog crops (not limited)'
          }
          onEditFarm={() => setFarmOpen(true)}
        />
      </div>

      <TimelineCard state={timeline} />

      {runs.status === 'loading' && <StateView kind="loading" title="Loading runs…" />}
      {runs.status === 'error' && <StateView kind="failed" title="Runs could not be loaded">{runs.error.message}</StateView>}
      {observeOnly && (
        <StateView kind="unavailable" title="Observe only for this farm">
          {OBSERVE_ONLY} The field history, map, data journey and evidence below are already real.
          <button type="button" className="btn btn--primary" onClick={() => onNavigate('rotation')}>
            Build rotations
          </button>
        </StateView>
      )}
      {runs.status === 'ready' && !run && runState.status !== 'running' && !observeOnly && (
        <StateView kind="empty" title="No comparison run yet">
          Press <strong>Run comparison</strong> to simulate current practice and the alternatives on the same historical weather.
        </StateView>
      )}

      {run && (
        <>
          <LiveRotation
            run={run}
            outdated={outdated}
            crops={cropMap}
            shifts={draft.shifts}
            onShift={(id, days) => setDraft((d) => ({ ...d, shifts: { ...d.shifts, [id]: days } }))}
            showRanges={showRanges}
            onShowRanges={setShowRanges}
            onExplore={() => document.getElementById('tradeoffs')?.scrollIntoView({ behavior: 'smooth' })}
          />

          <RunComparison
            strategies={views}
            run={{ nPaths: run.run.n_paths, sampleStartYear: sampleStart, sampleEndYear: sampleEnd }}
            axes={{ waterStress: axisFor(views.map((v) => v.waterStress)), soilCover: axisFor(views.map((v) => v.soilCover)) }}
            outdated={outdated}
            showRanges={showRanges}
            sourceNote={[
              `Weather: ${run.run.weather_source_id} (one source per run)`,
              `Soil: ${run.run.input_versions?.soil_profile_id ?? '—'} · crop parameters: FAO-56`,
            ]}
            onEvidence={() => onNavigate('evidence')}
            mode={{
              value: draft.mode,
              shown: run.run.mode,
              onChange: (mode) =>
                setDraft((d) => ({ ...d, mode, allocationMm: mode === 'fixed_allocation' ? (d.allocationMm ?? farmer?.irrigation_allocation_mm ?? null) : d.allocationMm })),
            }}
            cardNote={() => `${run.run.is_demo ? 'DEMO · ' : ''}Run ${run.run.id}${run.cached ? ' (cached)' : ''}`}
            infeasible={infeasible}
            coverageLabel="Coverage not yet evaluated → Evidence"
            details={(sid) => (
              <details>
                <summary className="small">All {Object.keys(METRICS).length} metrics</summary>
                <table className="metrics-table">
                  <tbody>
                    {Object.entries(METRICS).map(([m, meta]) => {
                      const r = resultFor(results, sid, m)
                      const d = deltas.find((x) => x.strategy_id === sid && x.metric === m)
                      if (!r) return null
                      return (
                        <tr key={m}>
                          <th scope="row">{meta.label}</th>
                          <td className="num">
                            {fmt(r.p50)} {r.unit}
                            <br />
                            <span className="muted">
                              {fmt(r.p10)}–{fmt(r.p90)}
                            </span>
                          </td>
                          <td className="num">
                            {d ? `Δ ${d.p50 != null && d.p50 > 0 ? '+' : ''}${fmt(d.p50)}` : sid === strategies.find((s) => s.is_baseline)?.id ? 'reference' : ''}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <p className="small muted">
                  {results.find((r) => r.strategy_id === sid)?.range_label}. Δ = strategy − current practice on matching paths.
                </p>
              </details>
            )}
          />

          <TradeOffs strategies={strategies} results={results} ranking={ranking} outdated={outdated} />
          <HarvestTable strategies={strategies} results={results} crops={cropMap} outdated={outdated} />
        </>
      )}

      <NextStep
        strategies={ranking.order.map((s) => ({ id: s.id, name: shortName(s.name) }))}
        outdated={outdated}
        lockReason={lockReason}
        onExport={(chosen, reason) =>
          api.createDecisionCard({
            site_id: siteId,
            run_id: run?.run.id ?? '',
            chosen_strategy_id: chosen,
            reason,
            priorities: { conserve_water: priorities.conserveWater, protect_soil: priorities.protectSoil },
          })
        }
      />

      <footer className="source-footer">
        <span>
          {run
            ? `Sources used by run ${run.run.id}: ${runSources.length ? runSources.map((s) => `${s?.provider} — ${s?.product}`).join(' · ') : run.source_ids.join(', ')}`
            : 'No run yet: no simulation sources to list.'}
        </span>
        <span>Historical weather is resampled: this is not a forecast. No NASA endorsement is implied.</span>
      </footer>

      <FarmDetailsDialog
        siteId={siteId}
        open={farmOpen}
        initial={farmer}
        crops={rotationCrops.status === 'ready' ? rotationCrops.data : []}
        soilSummary={soilSource ? `${soilSource.product} (${soilSource.id})` : 'none stored'}
        onClose={() => setFarmOpen(false)}
        onSaved={(ctx) => {
          setFarmer(ctx)
          setFarmOpen(false)
        }}
      />
    </>
  )
}

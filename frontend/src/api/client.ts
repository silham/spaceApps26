import type {
  CropProfile,
  DecisionCard,
  DecisionCardRequest,
  EnvironmentalTimeline,
  FarmerContext,
  JourneyStage,
  PairedDelta,
  ReplayTrace,
  Result,
  RunDetail,
  RunRequest,
  Site,
  Source,
  Strategy,
  Validation,
} from '../types/contracts'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

/** FastAPI returns `detail` as a string for our errors and as a list for request-validation errors. */
function detailText(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: unknown }).msg) : null))
      .filter(Boolean)
    return msgs.length ? msgs.join('; ').replace(/^Value error, /, '') : null
  }
  return null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown }
    throw new ApiError(res.status, detailText(body.detail) ?? res.statusText)
  }
  return (await res.json()) as T
}

const get = <T>(path: string) => request<T>(path)
const send = <T>(method: 'POST' | 'PUT', path: string, body: unknown) =>
  request<T>(path, { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
const q = encodeURIComponent

export interface Health {
  status: string
  api_version: string
  schema_version: string
  model_version: string
  demo_mode: boolean
}

/** Export links in a card are API-relative; the dev server and the build both serve the API under /api. */
export const apiUrl = (path: string) => `/api${path}`

export const api = {
  health: () => get<Health>('/health'),
  sites: () => get<Site[]>('/sites'),
  sources: () => get<Source[]>('/sources'),
  crops: () => get<CropProfile[]>('/crops'),
  validations: (siteId: string) => get<Validation[]>(`/validations?site_id=${q(siteId)}`),
  strategies: (siteId: string) => get<Strategy[]>(`/strategies?site_id=${q(siteId)}`),
  journey: (siteId: string) => get<JourneyStage[]>(`/journey/${q(siteId)}`),
  timeline: (siteId: string) => get<EnvironmentalTimeline>(`/sites/${q(siteId)}/timeline`),
  farmerContext: (siteId: string) => get<FarmerContext>(`/sites/${q(siteId)}/farmer-context`),
  saveFarmerContext: (siteId: string, ctx: FarmerContext) =>
    send<FarmerContext>('PUT', `/sites/${q(siteId)}/farmer-context`, ctx),
  runs: (siteId: string) => get<RunDetail[]>(`/runs?site_id=${q(siteId)}`),
  run: (runId: string) => get<RunDetail>(`/runs/${q(runId)}`),
  createRun: (req: RunRequest) => send<RunDetail>('POST', '/runs', req),
  results: (runId: string) => get<Result[]>(`/runs/${q(runId)}/results`),
  deltas: (runId: string) => get<PairedDelta[]>(`/runs/${q(runId)}/deltas`),
  replay: (runId: string, years: number[]) => get<ReplayTrace>(`/runs/${q(runId)}/replay?years=${years.join('-')}`),
  createDecisionCard: (req: DecisionCardRequest) => send<DecisionCard>('POST', '/decision-cards', req),
  decisionCards: (siteId: string) => get<DecisionCard[]>(`/decision-cards?site_id=${q(siteId)}`),
}

import type { JourneyStage, Result, SimulationRun, Site, Source, Strategy } from '../types/contracts'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new ApiError(res.status, body.detail ?? res.statusText)
  }
  return (await res.json()) as T
}

const get = <T>(path: string) => request<T>(path)

export interface Health {
  status: string
  api_version: string
  schema_version: string
  model_version: string
  demo_mode: boolean
}

export const api = {
  health: () => get<Health>('/health'),
  sites: () => get<Site[]>('/sites'),
  sources: () => get<Source[]>('/sources'),
  strategies: (siteId: string) => get<Strategy[]>(`/strategies?site_id=${encodeURIComponent(siteId)}`),
  results: (runId: string) => get<Result[]>(`/runs/${encodeURIComponent(runId)}/results`),
  journey: (siteId: string) => get<JourneyStage[]>(`/journey/${encodeURIComponent(siteId)}`),
  // The request body is not defined yet: the supported-edit set is open (docs/decisions.md D6).
  createRun: () => request<SimulationRun>('/runs', { method: 'POST' }),
}

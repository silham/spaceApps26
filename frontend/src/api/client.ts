import type { Result, Site, Source, Strategy } from '../types/contracts'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new ApiError(res.status, body.detail ?? res.statusText)
  }
  return (await res.json()) as T
}

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
}

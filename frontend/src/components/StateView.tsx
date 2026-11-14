import type { ReactNode } from 'react'

export type StateKind = 'loading' | 'empty' | 'missing' | 'failed' | 'unavailable'

const TITLES: Record<StateKind, string> = {
  loading: 'Loading…',
  empty: 'Nothing here yet',
  missing: 'Data missing',
  failed: 'Something failed',
  unavailable: 'Not available',
}

/** One look for every non-data state (guide §11 item 10), so empty, missing and failed never look alike. */
export function StateView({ kind, title, children }: { kind: StateKind; title?: string; children?: ReactNode }) {
  const role = kind === 'failed' ? 'alert' : 'status'
  return (
    <div className={`state ${kind === 'failed' ? 'state--failed' : ''}`} role={role}>
      <strong>{title ?? TITLES[kind]}</strong>
      {children}
    </div>
  )
}

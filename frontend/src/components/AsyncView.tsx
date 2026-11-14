import type { ReactNode } from 'react'
import type { AsyncState } from '../api/useAsync'

/** Shared loading / error / empty handling so every data view has these states. */
export function AsyncView<T>({
  state,
  isEmpty,
  children,
}: {
  state: AsyncState<T>
  isEmpty?: (data: T) => boolean
  children: (data: T) => ReactNode
}) {
  if (state.status === 'loading') return <p role="status">Loading…</p>
  if (state.status === 'error') return <p role="alert">Could not load: {state.error.message}</p>
  if (isEmpty?.(state.data)) return <p>No data yet.</p>
  return <>{children(state.data)}</>
}

import type { Result } from '../types/contracts'

/** p10/p50/p90 display. Always shows the contract's range_label wording, never "confidence". */
export function RangeBar({ result }: { result: Result }) {
  if (result.p50 == null) return <span>No result: {result.limitations?.join('; ') || 'unavailable'}</span>
  return (
    <span>
      {result.p50} {result.unit}{' '}
      <small>
        ({result.p10}–{result.p90}, {result.range_label}, n={result.sample_count})
      </small>
    </span>
  )
}

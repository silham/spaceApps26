import { ctl } from './ctl'

/** Visible label for demo data (AGENTS.md rule 2). Uses the Figma "Badge / Warning" component. */
export function DemoBadge({ label = 'DEMO DATA' }: { label?: string }) {
  return (
    <span role="note" className={ctl('warning')}>
      {label}
    </span>
  )
}

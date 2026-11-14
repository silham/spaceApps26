import { Badge } from './ui'

/** Visible label for demo data (AGENTS.md rule 2). Uses the Figma warning badge. */
export function DemoBadge({ label = 'DEMO DATA' }: { label?: string }) {
  return (
    <span role="note">
      <Badge tone="warning">{label}</Badge>
    </span>
  )
}

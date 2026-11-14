/** Visible label for demo data (AGENTS.md rule 2). Render wherever is_demo is true. */
export function DemoBadge() {
  return (
    <span
      role="note"
      style={{
        background: 'var(--color-demo-bg)',
        color: 'var(--color-demo)',
        border: '1px solid currentColor',
        borderRadius: 'var(--radius)',
        padding: '0 var(--space-2)',
        fontSize: 12,
        fontWeight: 700,
      }}
    >
      DEMO data
    </span>
  )
}

const STAGES = [
  ['collect', 'Collect', 'What arrived, from where, and for which dates?'],
  ['check', 'Check', 'What is missing, duplicated, rejected or flagged?'],
  ['clean', 'Clean', 'What changed, and why?'],
  ['handle_gaps', 'Handle gaps', 'Which values were estimated, and which remain unknown?'],
  ['align', 'Align', 'How were different scales and time intervals combined?'],
  ['extract', 'Extract', 'Which growing periods are suggested or confirmed?'],
  ['simulate', 'Simulate', 'How do the alternatives respond to the same conditions?'],
  ['validate', 'Validate', 'What was checked, against what, and with what limitations?'],
  ['compare', 'Compare', 'Which trade-offs matter to this farmer?'],
] as const

/** Data Journey: nine stage cards. TODO(M2): load /journey/{site_id} once implemented (M1/M3/M4/M5). */
export function DataJourneyScreen() {
  return (
    <section aria-labelledby="journey-h">
      <h2 id="journey-h">Data Journey</h2>
      <ol>
        {STAGES.map(([id, label, question]) => (
          <li key={id}>
            <strong>{label}</strong>: {question} <em>(status: not started)</em>
          </li>
        ))}
      </ol>
    </section>
  )
}

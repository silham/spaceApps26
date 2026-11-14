import type { JourneyStageName, StageStatus } from './types/contracts'

/** The nine pipeline stages (AGENTS.md rule 4), in order, with the question each card answers. */
export const STAGES: { id: JourneyStageName; label: string; question: string }[] = [
  { id: 'collect', label: 'Collect', question: 'What arrived, from where, and for which dates?' },
  { id: 'check', label: 'Check', question: 'What is missing, duplicated, rejected or flagged?' },
  { id: 'clean', label: 'Clean', question: 'What changed, and why?' },
  { id: 'handle_gaps', label: 'Handle gaps', question: 'Which values were estimated, and which remain unknown?' },
  { id: 'align', label: 'Align', question: 'How were different scales and time intervals combined?' },
  { id: 'extract', label: 'Extract', question: 'Which growing periods are suggested or confirmed?' },
  { id: 'simulate', label: 'Simulate', question: 'How do the alternatives respond to the same conditions?' },
  { id: 'validate', label: 'Validate', question: 'What was checked, against what, and with what limitations?' },
  { id: 'compare', label: 'Compare', question: 'Which trade-offs matter to this farmer?' },
]

/** Status is always text + glyph, never colour alone. ok/warning/not_started glyphs are from Figma. */
export const STATUS: Record<StageStatus, { glyph: string; label: string; warn: boolean }> = {
  ok: { glyph: '✓', label: 'OK', warn: false },
  warning: { glyph: '⚠', label: 'Warning', warn: true },
  not_started: { glyph: '⊖', label: 'Not started', warn: false },
  failed: { glyph: '✕', label: 'Failed', warn: true },
  unavailable: { glyph: '⊖', label: 'Unavailable', warn: false },
}

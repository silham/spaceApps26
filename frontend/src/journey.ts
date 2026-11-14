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

/** How a status is drawn. The frame defines three looks (OK, Warning, Not started); "failed" reuses
    the warning look and "unavailable" the not-started look, each with its own text. */
export type StatusKind = 'ok' | 'warning' | 'idle'

export const STATUS: Record<StageStatus, { label: string; kind: StatusKind }> = {
  ok: { label: 'OK', kind: 'ok' },
  warning: { label: 'Warning', kind: 'warning' },
  not_started: { label: 'Not started', kind: 'idle' },
  failed: { label: 'Failed', kind: 'warning' },
  unavailable: { label: 'Unavailable', kind: 'idle' },
}

export const KIND_TONE = { ok: 'success', warning: 'warning', idle: 'neutral' } as const

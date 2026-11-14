import type { JourneyStageName, StageStatus } from './types/contracts'

/** The nine pipeline stages (AGENTS.md rule 4), in order, with the question each card answers. */
export const STAGES: { id: JourneyStageName; label: string; question: string; meaning: string }[] = [
  { id: 'collect', label: 'Collect', question: 'What arrived, from where, and for which dates?', meaning: 'We list every data source we downloaded, what dates it covers, and keep an untouched copy so anything can be re-checked.' },
  { id: 'check', label: 'Check', question: 'What is missing, duplicated, rejected or flagged?', meaning: 'We count what arrived against what we expected. Missing, duplicated or suspicious values are flagged here, not hidden.' },
  { id: 'clean', label: 'Clean', question: 'What changed, and why?', meaning: 'Obvious errors are removed and units are made consistent. Both the raw and the cleaned value stay on record.' },
  { id: 'handle_gaps', label: 'Handle gaps', question: 'Which values were estimated, and which remain unknown?', meaning: 'Short gaps in some variables may be estimated by a stated method. Missing rainfall is never filled in: it is never treated as zero.' },
  { id: 'align', label: 'Align', question: 'How were different scales and time intervals combined?', meaning: 'Sources have different pixel sizes and time steps. We line them up to one daily series for the field and show each source\'s real footprint.' },
  { id: 'extract', label: 'Extract', question: 'Which growing periods are suggested or confirmed?', meaning: 'Satellite greenness suggests when growing seasons start and end. It is evidence of activity, not proof of which crop grew.' },
  { id: 'simulate', label: 'Simulate', question: 'How do the alternatives respond to the same conditions?', meaning: 'Every strategy is run through a daily soil-water model on the same historical weather, many times, so differences come from the strategy.' },
  { id: 'validate', label: 'Validate', question: 'What was checked, against what, and with what limitations?', meaning: 'We check our methods against independent records and say plainly what has not been tested yet.' },
  { id: 'compare', label: 'Compare', question: 'Which trade-offs matter to this farmer?', meaning: 'Each alternative is compared with current practice on the very same weather, path by path. The farmer decides what matters.' },
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

/**
 * DEMO / illustrative content of Figma frame 3:2 ("Farm Time Machine / Primary dashboard").
 *
 * Nothing here is data or a model output. It is the designer's illustrative content, and the
 * dashboard always shows it under the Figma's own DEMO labels ("DEMO DATA", "DEMO / illustrative
 * previous-run results", "Illustrative statuses", "Illustrative map"). Replace each field with the
 * API payload as the contract grows to cover it (soil-cover results, paired deltas, run metadata,
 * crop names). Unknown values stay `null` and render as "—".
 */
import type { JourneyStageName, StageStatus } from '../types/contracts'

export type Tone = 'baseline' | 'water' | 'soil'

export interface RotationCellView {
  label: string
  /** 'crop' renders the ♧ glyph, 'none' the · · · glyph used for bare soil and fallow. */
  glyph: 'crop' | 'none'
  warning?: boolean
}

export interface PairedDeltaView {
  direction: 'benefit' | 'disadvantage'
  label: string
  medianDays: number | null
  p10Days: number | null
  p90Days: number | null
  betterPct: number | null
}

export interface MetricView {
  p50: number | null
  p10: number | null
  p90: number | null
  /** null = this strategy is the reference (paired Δ = 0). */
  paired: PairedDeltaView | null
}

export interface StrategyView {
  id: string
  name: string
  tone: Tone
  cells: [RotationCellView, RotationCellView, RotationCellView]
  waterStress: MetricView
  soilCover: MetricView
}

const awaiting = (direction: PairedDeltaView['direction'], label: string): PairedDeltaView => ({
  direction,
  label,
  medianDays: null,
  p10Days: null,
  p90Days: null,
  betterPct: null,
})

export const figmaDemo = {
  isDemo: true,
  farmLabel: 'Demo farm · site pending',
  displayWindow: '2017–2019',
  run: {
    id: 'R-014',
    sampleStartYear: 1984,
    sampleEndYear: 2019,
    nPaths: 500,
    horizonYears: 5,
    excludedNote: '1981–1983 excluded: solar gap  ·  2020–2025 reserved for final test',
  },
  /** Inputs edited since run R-014; the frame shows this outdated state. */
  changedSinceRun: ['irrigation limit'],
  journey: [
    ['collect', 'ok'],
    ['check', 'ok'],
    ['clean', 'ok'],
    ['handle_gaps', 'warning'],
    ['align', 'ok'],
    ['extract', 'warning'],
    ['simulate', 'ok'],
    ['validate', 'not_started'],
    ['compare', 'ok'],
  ] as [JourneyStageName, StageStatus][],
  field: { label: 'Demo field · 4.2 ha' },
  priorities: { conserveWater: 68, protectSoil: 78 },
  constraints: {
    irrigationLimit: '120 mm / season',
    soilProfile: 'Estimated',
    equipment: 'Standard',
    mustIncludeMarketCrop: false,
  },
  replay: {
    year: 2018,
    startDate: '2018-06-18',
    /** Illustrative calendar for the three timeline columns. Only the 18 Jun boundary comes from
        the frame (its playhead sits there); the second boundary is a placeholder. */
    betweenSeasonsStart: '2018-06-18',
    seasonTwoStart: '2018-10-01',
  },
  strategies: [
    {
      id: 'current',
      name: 'Current practice',
      tone: 'baseline',
      cells: [
        { label: 'Maize', glyph: 'crop' },
        { label: 'Bare soil', glyph: 'none' },
        { label: 'Maize', glyph: 'crop' },
      ],
      waterStress: { p50: 21, p10: 14, p90: 30, paired: null },
      soilCover: { p50: 210, p10: 195, p90: 224, paired: null },
    },
    {
      id: 'water-saving',
      name: 'Water-saving',
      tone: 'water',
      cells: [
        { label: 'Sorghum', glyph: 'crop' },
        { label: 'Fallow', glyph: 'none' },
        { label: 'Cowpea', glyph: 'crop' },
      ],
      waterStress: { p50: 12, p10: 7, p90: 19, paired: awaiting('benefit', 'fewer stress days') },
      soilCover: { p50: 190, p10: 178, p90: 203, paired: awaiting('disadvantage', 'fewer cover days') },
    },
    {
      id: 'soil-protecting',
      name: 'Soil-protecting',
      tone: 'soil',
      cells: [
        { label: 'Maize', glyph: 'crop' },
        { label: 'Cover crop', glyph: 'crop', warning: true },
        { label: 'Cowpea', glyph: 'crop' },
      ],
      waterStress: { p50: 17, p10: 11, p90: 25, paired: awaiting('benefit', 'fewer stress days') },
      soilCover: { p50: 246, p10: 231, p90: 260, paired: awaiting('benefit', 'more cover days') },
    },
  ] as StrategyView[],
  rotationWarning: 'Cover crop: uses water the next crop may need.',
  metricSourceNote: ['Water stress: POWER + demo crop/soil inputs', 'Cover: demo calendar + management assumptions'],
  sourceFooter: 'Demo run rainfall: NASA POWER only  ·  Vegetation context: MODIS',
} as const

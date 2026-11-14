import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { PairedDelta, Result, RunDetail, Strategy } from '../types/contracts'
import {
  axisFor,
  changesSince,
  draftProblem,
  driestWindow,
  pairedView,
  rankStrategies,
  requestFromDraft,
} from './model.ts'

const strategy = (id: string, feasible = true): Strategy => ({
  id,
  site_id: 's',
  name: id.toUpperCase(),
  seasons: [],
  feasibility: { feasible, reasons: feasible ? [] : ['TEST reason'] },
})
const result = (strategy_id: string, metric: string, p50: number): Result => ({
  id: `${strategy_id}-${metric}`,
  run_id: 'r',
  strategy_id,
  metric,
  unit: 'x',
  p10: p50 - 1,
  p50,
  p90: p50 + 1,
  sample_count: 20,
  source_ids: [],
})

describe('rankStrategies', () => {
  const ss = [strategy('a'), strategy('b'), strategy('c', false)]
  const rs = [
    result('a', 'irrigation_mm', 100),
    result('a', 'possible_low_cover_days', 50),
    result('b', 'irrigation_mm', 200),
    result('b', 'possible_low_cover_days', 10),
    result('c', 'irrigation_mm', 0),
  ]

  it('orders by the higher-weighted priority and never ranks infeasible options', () => {
    const water = rankStrategies(ss, rs, { conserveWater: 80, protectSoil: 20 })
    assert.deepEqual(water.order.map((s) => s.id), ['a', 'b'])
    assert.deepEqual(water.excluded.map((s) => s.id), ['c'])
    const soil = rankStrategies(ss, rs, { conserveWater: 20, protectSoil: 80 })
    assert.deepEqual(soil.order.map((s) => s.id), ['b', 'a'])
    assert.match(soil.rule, /No combined score/)
  })
})

describe('draft edits', () => {
  const run = {
    request: { site_id: 's', mode: 'fixed_allocation', allocation_mm: 300, planting_shift_days: { a: 5 } },
  } as unknown as RunDetail

  it('lists exactly what changed since the shown run', () => {
    assert.deepEqual(changesSince(run, { mode: 'fixed_allocation', allocationMm: 300, shifts: { a: 5 } }, {}), [])
    assert.deepEqual(changesSince(run, { mode: 'fixed_allocation', allocationMm: 250, shifts: { a: 5 } }, {}), [
      'irrigation limit',
    ])
    assert.deepEqual(
      changesSince(run, { mode: 'irrigation_needed', allocationMm: null, shifts: { a: 0 } }, { a: 'A' }),
      ['irrigation mode', 'planting date (A)'],
    )
    assert.deepEqual(changesSince(null, { mode: 'irrigation_needed', allocationMm: null, shifts: {} }, {}), [])
  })

  it('refuses unsupported edits before sending them', () => {
    assert.match(draftProblem({ mode: 'fixed_allocation', allocationMm: null, shifts: {} }) ?? '', /irrigation limit/)
    assert.match(draftProblem({ mode: 'irrigation_needed', allocationMm: null, shifts: { a: 15 } }) ?? '', /±14/)
    assert.equal(draftProblem({ mode: 'irrigation_needed', allocationMm: null, shifts: { a: 14 } }), null)
  })

  it('drops zero shifts and the allocation outside fixed mode', () => {
    assert.deepEqual(requestFromDraft('s', { mode: 'irrigation_needed', allocationMm: 200, shifts: { a: 0, b: -3 } }), {
      site_id: 's',
      mode: 'irrigation_needed',
      allocation_mm: null,
      planting_shift_days: { b: -3 },
    })
  })
})

describe('presentation helpers', () => {
  it('words a paired difference from the share of paths, not from medians', () => {
    const d = {
      strategy_id: 'b',
      metric: 'water_stress_days',
      p10: 2,
      p50: 8,
      p90: 25,
      share_better: 0.14,
      share_worse: 0.8,
    } as PairedDelta
    const v = pairedView(d)
    assert.equal(v.direction, 'disadvantage')
    assert.equal(v.label, 'more stress days')
    assert.equal(v.betterPct, 14)
  })

  it('pads axes and ignores missing values', () => {
    const views = [
      { p10: 10, p50: 20, p90: 30, paired: null },
      { p10: null, p50: null, p90: null, paired: null },
    ]
    assert.deepEqual(axisFor(views), [9, 31])
  })

  it('never treats unknown rain as a dry year', () => {
    const run = {
      replay_windows: [
        { years: [1, 2], enabled: true, in_sample_pool: true, rain_mm: null },
        { years: [2, 3], enabled: true, in_sample_pool: true, rain_mm: 500 },
        { years: [3, 4], enabled: false, in_sample_pool: true, rain_mm: 100 },
      ],
    } as unknown as RunDetail
    assert.deepEqual(driestWindow(run)?.years, [2, 3])
  })
})

import { expect, test } from '@playwright/test'
import { mockSignedIn, TEST_USER } from './auth'

const param = (value: number) => ({ value, unit: 'days', reference: 'TEST' })
const crop = (id: string, name: string, days: number[]) => ({
  id,
  name,
  stage_lengths_days: { ini: param(days[0]!), dev: param(days[1]!), mid: param(days[2]!), late: param(days[3]!) },
})
const CROPS = [crop('soybean', 'Soybean', [20, 35, 60, 25]), crop('winter-wheat', 'Winter wheat', [160, 75, 75, 25])]
const FARM = { id: 'f1', owner_user_id: TEST_USER.id, name: 'North field', archived: false, latitude: 38, longitude: -100, timezone: 'UTC', area_ha: null, is_demo: false }
const rule = (rule_id: string, label: string, status: string) => ({ rule_id, label, status, explanation: 'TEST', reference: 'TEST' })
const m = (metric: string, p50: number, delta: number | null = null, season_index: number | null = null) => ({
  metric, unit: metric.endsWith('mm') ? 'mm' : 'days', season_index, p10: p50 - 10, p50, p90: p50 + 10, delta_p50_vs_current: delta,
})
const CANDIDATE = {
  rank: 1,
  name: 'Soybean → Winter wheat (irrigated)',
  seasons: [
    { crop_id: 'soybean', plant_date: '2027-04-01', end_date: '2027-08-18', irrigation_rule: null },
    { crop_id: 'winter-wheat', plant_date: '2027-09-01', end_date: '2028-07-31', irrigation_rule: 'refill_to_field_capacity_at_raw' },
  ],
  metrics: [m('possible_low_cover_days', 436, 23), m('irrigation_mm', 889, -468), { ...m('relative_yield_pct', 63, null, 0), unit: '%' }],
  soil_health: [rule('family_change', 'Crop families alternate', 'met'), rule('legume_before_nonlegume', 'A legume comes before a non-legume', 'met')],
  soil_rules_met: 2,
  non_dominated: true,
  why: ['Rank 1 in your order: soil-health rules met, then possible low-cover days, then irrigation.'],
  trade_offs: ['Irrigation: 468 mm less than your current practice.'],
}

test('suggested rotations: ask, wait, read the trade-offs and use one in the planner', async ({ page }) => {
  await mockSignedIn(page)
  let asked: Record<string, unknown> | null = null
  let polls = 0
  await page.route(/\/api\/sites(\?.*)?$/, (r) => r.fulfill({ json: [FARM] }))
  await page.route(/\/api\/crops\?for_rotations=true$/, (r) => r.fulfill({ json: CROPS }))
  await page.route(/\/api\/strategies\?site_id=f1$/, (r) => r.fulfill({ json: [] }))
  await page.route(/\/api\/sites\/f1\/horizon$/, (r) =>
    r.fulfill({ json: { site_id: 'f1', observed_end: '2026-11-11', start: '2026-11-12', end: '2028-11-11', weather_source_id: 'w' } }),
  )
  await page.route(/\/api\/sites\/f1\/(outlook|refresh)$/, (r) => r.fulfill({ status: 409, json: { detail: 'TEST' } }))
  const base = { id: 'rec1', site_id: 'f1', request: {}, created_at: '2026-11-15T00:00:00Z' }
  await page.route(/\/api\/sites\/f1\/recommendations$/, (r) => {
    asked = r.request().postDataJSON()
    return r.fulfill({ status: 202, json: { ...base, status: 'queued', progress: 0 } })
  })
  await page.route(/\/api\/sites\/f1\/recommendations\/rec1$/, (r) => {
    polls += 1
    return r.fulfill({
      json:
        polls < 2
          ? { ...base, status: 'running', progress: 0.4, message: 'Simulating candidates' }
          : {
              ...base, status: 'done', progress: 1, candidates_considered: 135, candidates: [CANDIDATE], current_practice: null,
              n_paths: 100, range_label: 'central 80% simulation range (p10–p90)', horizon_start: '2026-11-12', horizon_end: '2028-11-11',
              source_ids: ['power_test', 'seas5_test'], assumptions: ['TEST assumption'], limitations: [],
            },
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Open farm' }).click()
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Rotation planner' }).click()
  const panel = page.getByRole('region', { name: 'Suggest rotations for me' })
  await panel.getByLabel('What matters most, in order').selectOption({ label: 'Soil health (crop families, legumes) › Keep the soil covered › Use less irrigation' })
  await panel.getByLabel('Irrigation is possible').uncheck()
  await panel.getByRole('button', { name: 'Find rotations' }).click()
  await expect(panel.getByText('Simulating candidates')).toBeVisible()
  const option = panel.getByRole('article', { name: 'Option 1' })
  await expect(option).toBeVisible()
  expect(asked).toMatchObject({ priorities: ['soil_health', 'cover', 'irrigation'], irrigation_allowed: false, min_relative_yield_pct: 60 })
  await expect(option.getByText('-468 mm vs current')).toBeVisible()
  await expect(option.getByText('A legume comes before a non-legume')).toBeVisible()
  await expect(panel.getByText(/135 rotations considered/)).toBeVisible()

  await option.getByRole('button', { name: 'Use this rotation' }).click()
  await expect(page.getByRole('region', { name: 'Rotation 2' })).toBeVisible()
  await expect(page.getByLabel('Rotation 2 name')).toHaveValue('Soybean → Winter wheat (irrigated)')
  await expect(page.getByLabel('Rotation 2 season 2 crop')).toHaveValue('winter-wheat')
})

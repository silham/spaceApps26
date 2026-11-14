import { expect, test } from '@playwright/test'
import { mockSignedIn, TEST_USER } from './auth'

const FARM = { id: 'f1', owner_user_id: TEST_USER.id, name: 'North field', archived: false, latitude: 38, longitude: -100, timezone: 'UTC', area_ha: null, is_demo: false }
const dates = ['2026-11-12', '2026-11-13', '2026-11-14']
const band = (a: number, b: number, c: number) => ({ p10: [a, a, a], p50: [b, b, b], p90: [c, c, c] })
const OUTLOOK = {
  site_id: 'f1',
  observed_end: '2026-11-11',
  horizon_start: '2026-11-12',
  horizon_end: '2028-11-11',
  forecast_source_id: 'seas5_test',
  forecast_retrieved_at: '2026-11-15T00:00:00Z',
  odds: [
    { window: 'Nov–Jan', months: ['2026-11-01', '2026-12-01', '2027-01-01'], variable: 'rain', below: 0.04, near: 0.1, above: 0.86, member_count: 51 },
    { window: 'Nov–Jan', months: ['2026-11-01', '2026-12-01', '2027-01-01'], variable: 'temperature', below: 0.37, near: 0.28, above: 0.35, member_count: 51 },
  ],
  effective_sample_size: 10,
  dates,
  rain_mm: band(0, 1, 5),
  rain_cumulative_mm: band(0, 2, 9),
  tmin_c: band(-5, 0, 3),
  tmax_c: band(5, 10, 15),
  storage_mm: band(180, 200, 210),
  soil_water_now_mm: 205,
  soil_water_capacity_mm: 214.4,
  initial_assumption: 'Soil water now assumes bare fallow over the last year (what is on the field was not entered).',
  n_paths: 100,
  range_label: 'central 80% simulation range (p10–p90)',
  assumptions: ['Rain and temperature terciles, and successive windows, are treated as independent.'],
  source_ids: ['power_test', 'seas5_test'],
  attribution: 'Weather data by Open-Meteo.com',
  limitations: ['Soil water is simulated by the FAO-56 water balance, not measured.'],
  is_demo: false,
}

test('the coming months: forecast odds in words, simulated soil water now, sources and attribution', async ({ page }) => {
  await mockSignedIn(page)
  let refreshed = 0
  await page.route(/\/api\/sites(\?.*)?$/, (r) => r.fulfill({ json: [FARM] }))
  await page.route(/\/api\/sites\/f1\/outlook$/, (r) => r.fulfill({ json: OUTLOOK }))
  await page.route(/\/api\/sites\/f1\/refresh$/, (r) => {
    refreshed += 1
    return r.fulfill({ status: 202, json: { site_id: 'f1', status: 'done', steps: [], has_strategies: false } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Open farm' }).click()

  const card = page.getByRole('region', { name: 'The coming months' })
  await expect(card).toBeVisible()
  await expect(card.getByText('86% of members wetter than usual')).toBeVisible()
  await expect(card.getByText('No clear signal')).toBeVisible() // 37/28/35: no tercile stands out
  await expect(card.getByText('205 of 214 mm')).toBeVisible()
  await expect(card.getByText(/assumes bare fallow/)).toBeVisible()
  await expect(card.getByRole('link', { name: 'Weather data by Open-Meteo.com' })).toBeVisible()
  await expect(card.getByText(/Sources: power_test, seas5_test/)).toBeVisible()
  await expect(card.getByText(/central 80% simulation range/)).toBeVisible()
  expect(refreshed).toBeGreaterThan(0) // newer weather and forecast are requested when the farm opens

  await card.getByRole('button', { name: 'Tell us what is on the field' }).click()
  await expect(page.getByRole('group', { name: 'On the field now' })).toBeVisible()
})

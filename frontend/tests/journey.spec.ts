import { expect, test } from '@playwright/test'
import { mockSignedIn } from './auth'

// SYNTHETIC payload used only to exercise rendering (shapes copied from backend/src/ftm/data/journey.py,
// data/pipeline/run.py, validation/phenology.py and validation/report.py). None of these numbers is real data.
const stage = (name: string, extra: Record<string, unknown> = {}) => ({
  stage: name, status: 'ok', summary: `${name} summary`, source_ids: ['src_a'], processing_run_id: 'run_x', details: {}, is_demo: false, ...extra,
})
const days = Array.from({ length: 40 }, (_, i) => new Date(Date.UTC(2020, 0, 1 + i * 16)).toISOString().slice(0, 10))
const square = (x: number, y: number, d: number) => ({ type: 'Polygon', coordinates: [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]] })
const journey = [
  stage('collect', {
    chart: { type: 'coverage_strip', sources: [{ source_id: 'src_a', product: 'Weather', coverage_start: '1984-01-01', coverage_end: '2025-12-31' }] },
    details: { missing: [], sources: [{ source_id: 'src_a', provider: 'P', product: 'Weather', version: 'v1', license: 'CC0', limitations: 'Gridded estimate' }] },
  }),
  stage('check', { chart: { type: 'missing_timeline', series: { PRECTOTCORR: ['2020-03-01', '2020-03-02'], T2M: [] } }, details: { satellite_vegetation_qa: { good: 10, cloudy: 3 } } }),
  stage('clean', { chart: { type: 'raw_vs_clean', series: { PRECTOTCORR: [{ date: '2020-03-01', raw: 1, processed: 1, flag: null }, { date: '2020-03-02', raw: null, processed: null, flag: 'missing' }] } } }),
  stage('handle_gaps', { status: 'warning', chart: { type: 'gap_markers', gaps: [{ variable: 'PRECTOTCORR', start: '2020-03-01', end: '2020-03-02', length_days: 2, resolved: false, method: null, why_unresolved: 'Rain is never interpolated.' }] } }),
  stage('align', { chart: { type: 'footprint_map', layers: { type: 'FeatureCollection', features: [
    { type: 'Feature', geometry: square(-100.926, 38.014, 0.003), properties: { layer: 'field_boundary', label: 'Field boundary (approximate)' } },
    { type: 'Feature', geometry: square(-100.927, 38.013, 0.004), properties: { layer: 'source_footprint', label: 'MODIS pixel' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-101.0, 38.0] }, properties: { layer: 'weather_grid_point', label: 'grid' } },
  ] } } }),
  stage('extract', { status: 'warning', chart: { type: 'vi_curve', dates: days, ndvi_qa: days.map((_, i) => (i % 7 ? 0.3 : null)), ndvi_smooth: days.map((_, i) => 0.3 + 0.01 * i), seasons: [{ start: days[5], peak: days[15], end: days[25], fallback: true }], low_cover: [[days[30], days[35]]] }, details: { caveats: ['Satellite does not identify the crop.'] } }),
  stage('simulate', { status: 'not_started', source_ids: [], processing_run_id: null }),
  stage('validate', { status: 'warning', chart: { type: 'observed_vs_detected', points: [{ year: 2010, reference_doy: 120, detected_doy: 140, split: 'tuning' }, { year: 2016, reference_doy: 118, detected_doy: null, split: 'development' }] }, details: { failures: ['Season missed in 2016'], not_yet_evaluated: ['Held-out years 2020–2025'] } }),
  stage('compare', { status: 'not_started', source_ids: [], processing_run_id: null }),
]

test('Data Journey renders nine cards from the API payload, with sources, failures and the map', async ({ page }) => {
  await mockSignedIn(page)
  await page.route(/\/api\/sites(\?.*)?$/, (r) => r.fulfill({ json: [{ id: 'f1', owner_user_id: 'usr_test', name: 'Test field', latitude: 38, longitude: -100.9, timezone: 'America/Chicago' }] }))
  await page.route(/\/api\/journey\/f1$/, (r) => r.fulfill({ json: journey }))
  page.on('pageerror', (e) => console.log('PAGEERR', e.message))
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Data Journey' }).click()
  await expect(page.getByRole('heading', { level: 2 })).toHaveCount(9)
  await expect(page.getByText('Failures')).toBeVisible()
  await expect(page.getByText('Season missed in 2016')).toBeVisible()
  await expect(page.getByText('Held-out years 2020–2025')).toBeVisible()
  await expect(page.getByText(/Possible low vegetation cover/)).toBeVisible()
  await expect(page.getByText('Field boundary (approximate)')).toBeVisible()
  await expect(page.getByText(/Sources: src_a · run run_x/).first()).toBeVisible()
  await expect(page.locator('canvas').first()).toBeVisible()
  await page.screenshot({ path: 'test-results/journey.png', fullPage: true })
})

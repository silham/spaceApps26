import { expect, test } from '@playwright/test'
import { mockSignedIn, TEST_USER } from './auth'

const param = (value: number) => ({ value, unit: 'days', reference: 'TEST' })
const crop = (id: string, name: string, days: number[]) => ({
  id,
  name,
  stage_lengths_days: { ini: param(days[0]!), dev: param(days[1]!), mid: param(days[2]!), late: param(days[3]!) },
})
const CROPS = [crop('maize-grain', 'Maize, field (grain)', [30, 40, 50, 50]), crop('soybean', 'Soybean', [20, 35, 60, 25])]
const FARM = { id: 'f1', owner_user_id: TEST_USER.id, name: 'North field', archived: false, latitude: 38, longitude: -100, timezone: 'UTC', area_ha: null, is_demo: false }

test('build rotations: the planner validates, then saves and runs the comparison', async ({ page }) => {
  await mockSignedIn(page)
  let saved: { rotations: { name: string; seasons: Record<string, unknown>[] }[] } | null = null
  let ran = false
  await page.route(/\/api\/sites(\?.*)?$/, (r) => r.fulfill({ json: [FARM] }))
  await page.route(/\/api\/crops\?for_rotations=true$/, (r) => r.fulfill({ json: CROPS }))
  await page.route(/\/api\/strategies\?site_id=f1$/, (r) => r.fulfill({ json: [] }))
  await page.route(/\/api\/sites\/f1\/rotations$/, (r) => {
    expect(r.request().method()).toBe('PUT')
    expect(r.request().headers()['x-ftm-request']).toBe('1')
    saved = r.request().postDataJSON()
    return r.fulfill({ json: [] })
  })
  await page.route(/\/api\/runs$/, (r) => {
    ran = true
    return r.fulfill({ status: 409, json: { detail: 'TEST: the engine is not reachable in this mock' } })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Open farm' }).click()
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Rotation planner' }).click()
  await expect(page.getByRole('heading', { name: 'Rotation planner' })).toBeVisible()

  const save = page.getByRole('button', { name: 'Save and compare' })
  await expect(save).toBeDisabled() // no crop chosen yet
  await expect(page.getByText('Rotation 1, season 1: choose a crop.')).toBeVisible()

  await page.getByLabel('Rotation 1 season 1 crop').selectOption('maize-grain')
  await page.getByLabel('Planting date').fill('2027-04-25')
  await expect(page.getByText('Harvest about 2027-10-12 (170 days after planting).')).toBeVisible()
  await page.getByRole('radio', { name: 'Irrigated' }).click()
  await page.getByLabel('Your usual yield (t/ha), optional').fill('11')
  await expect(save).toBeEnabled()

  // A second season that starts before the first is harvested is refused in words, before any request.
  await page.getByRole('button', { name: '+ Add a season' }).click()
  await page.getByLabel('Rotation 1 season 2 crop').selectOption('soybean')
  await page.getByLabel('Planting date').nth(1).fill('2027-08-01')
  await expect(page.getByText(/season 2 starts before season 1 is harvested/)).toBeVisible()
  await expect(save).toBeDisabled()
  await page.getByLabel('Planting date').nth(1).fill('2027-10-20')
  await expect(save).toBeEnabled()

  // Up to three rotations.
  await page.getByRole('button', { name: '+ Add a rotation to compare' }).click()
  await page.getByRole('button', { name: '+ Add a rotation to compare' }).click()
  await expect(page.getByRole('button', { name: '+ Add a rotation to compare' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Remove', exact: true }).last().click()
  await page.getByRole('button', { name: 'Remove', exact: true }).last().click()
  await save.click()
  await expect(page.getByText('TEST: the engine is not reachable in this mock')).toBeVisible()
  expect(ran).toBe(true)
  expect(saved).toEqual({
    rotations: [
      {
        name: 'Current practice',
        seasons: [
          { crop_id: 'maize-grain', plant_date: '2027-04-25', irrigated: true, usual_yield_t_ha: 11 },
          { crop_id: 'soybean', plant_date: '2027-10-20', irrigated: false, usual_yield_t_ha: null },
        ],
      },
    ],
  })
  // The rotations were saved even though the run failed: the user can still open the overview.
  await expect(page.getByRole('button', { name: 'Open the overview anyway' })).toBeVisible()
})

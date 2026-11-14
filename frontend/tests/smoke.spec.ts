import { expect, test, type Page } from '@playwright/test'
import { mockSignedIn } from './auth'

// The illustrative Figma overview now appears only for a farm marked DEMO in the signed-in account.
async function openDemoFarm(page: Page) {
  await mockSignedIn(page)
  const demo = { id: 'demo', owner_user_id: 'usr_test', name: 'DEMO farm', latitude: 38, longitude: -100, timezone: 'UTC', is_demo: true }
  await page.route(/\/api\/sites(\?.*)?$/, (r) => r.fulfill({ json: [demo] }))
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Overview' }).click()
}

test('app shell renders the views and the overview dashboard', async ({ page }) => {
  await openDemoFarm(page)
  const nav = page.getByRole('navigation', { name: 'Main' })
  for (const name of ['My farms', 'Overview', 'Rotation planner', 'Data Journey', 'Evidence & validation']) {
    await expect(nav.getByRole('button', { name })).toBeVisible()
  }
  await expect(page.getByRole('heading', { name: 'Your farm. Different futures.' })).toBeVisible()
  await expect(page.getByText('DEMO DATA')).toBeVisible()
})

test('editing a constraint keeps results marked outdated and export disabled', async ({ page }) => {
  await openDemoFarm(page)
  await page.getByLabel('Must include a market crop').check()
  await expect(page.getByText(/Irrigation limit and market-crop requirement changed/)).toBeVisible()
  await expect(page.getByRole('button', { name: /Export decision card/ })).toBeDisabled()
})

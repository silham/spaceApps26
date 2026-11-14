import { expect, test } from '@playwright/test'

test('app shell renders the four views and the overview dashboard', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: 'Main' })
  for (const name of ['Overview', 'Rotation planner', 'Data Journey', 'Evidence & validation']) {
    await expect(nav.getByRole('button', { name })).toBeVisible()
  }
  await expect(page.getByRole('heading', { name: 'Your farm. Different futures.' })).toBeVisible()
  await expect(page.getByText('DEMO DATA')).toBeVisible()
})

test('editing a constraint keeps results marked outdated and export disabled', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Must include a market crop').check()
  await expect(page.getByText(/irrigation limit and market-crop requirement changed/)).toBeVisible()
  await expect(page.getByRole('button', { name: /Export decision card/ })).toBeDisabled()
})

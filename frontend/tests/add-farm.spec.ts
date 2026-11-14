import { expect, test } from '@playwright/test'
import { API, registerInUi } from './auth'

// Real API (network needed for NASA POWER / SoilGrids). Skipped when the API is not running.
test('add a farm anywhere: place, outline, load, open observe-only', async ({ page, request }) => {
  const ok = await request.get(`${API}/health`).then((r) => r.ok()).catch(() => false)
  test.skip(!ok, 'API not running')
  test.setTimeout(600_000)

  // A new account has no farms, so My farms opens with the add-farm panel.
  await registerInUi(page, 'addfarm')
  await expect(page.getByRole('heading', { name: /Add a farm: where is your field/ })).toBeVisible()

  // Coordinates typed (the map click path is the same state); a farm in Mato Grosso, Brazil.
  await page.getByLabel('Latitude').fill('-12.55')
  await page.getByLabel('Longitude').fill('-55.72')
  await page.getByLabel('Farm name').fill('Sorriso test field')
  await page.getByRole('button', { name: 'Load this farm' }).click()
  await expect(page.getByText(/NASA POWER daily/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open this farm' })).toBeVisible({ timeout: 540_000 })
  await page.getByRole('button', { name: 'Open this farm' }).click()

  await expect(page.getByText('Observe only for this farm')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run comparison' })).toBeDisabled()
  await expect(page.getByRole('heading', { name: 'Field history' })).toBeVisible()
})

import { expect, test } from '@playwright/test'

// Runs against the real API seeded with ks-field-2 (make demo-load). Skipped when that site is not loaded.
test('full story on the live API: edit, rerun, replay, decision card', async ({ page, request }) => {
  const sites = await request.get('http://localhost:8000/sites').then((r) => r.json()).catch(() => [])
  test.skip(!Array.isArray(sites) || !sites.some((s: { id: string }) => s.id === 'ks-field-2'), 'ks-field-2 is not loaded')
  test.setTimeout(120_000)

  await page.goto('/')
  await page.getByRole('combobox', { name: 'Farm' }).selectOption('ks-field-2')
  await expect(page.getByRole('heading', { name: 'Your farm. Different futures.' })).toBeVisible()

  // First run (or the stored one).
  const empty = page.getByText('No comparison run yet')
  if (await empty.isVisible().catch(() => false)) await page.getByRole('button', { name: 'Run comparison' }).first().click()
  await expect(page.getByText(/Compare 3 rotations on the same weather/)).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText(/central 80% simulation range/).first()).toBeVisible()

  // An edit makes results outdated and locks the export.
  await page.getByRole('button', { name: /Plant Current practice one day later/ }).click()
  await expect(page.getByText('Results outdated')).toBeVisible()
  await expect(page.getByRole('button', { name: /Export decision card/ })).toBeDisabled()

  // Rerun clears the banner.
  await page.getByRole('button', { name: 'Refresh results' }).click()
  await expect(page.getByText('Results outdated')).toBeHidden({ timeout: 60_000 })

  // Replay loads a trace for the shared weather.
  await page.getByRole('button', { name: 'Replay a dry year' }).click()
  await expect(page.getByText(/one path, so no range/)).toBeVisible({ timeout: 30_000 })

  // Decision card.
  await page.getByRole('combobox', { name: 'Choose a strategy' }).selectOption({ index: 1 })
  await page.getByPlaceholder(/Record your reason/).fill('Test reason')
  await page.getByRole('button', { name: /Export decision card/ }).click()
  await expect(page.getByText(/Decision card saved/)).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('link', { name: 'Download PDF' })).toBeVisible()
})

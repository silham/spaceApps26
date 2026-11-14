import { expect, test } from '@playwright/test'

test('app shell renders the four steps', async ({ page }) => {
  await page.goto('/')
  for (const name of ['Observe', 'Experiment', 'Decide', 'Data Journey']) {
    await expect(page.getByRole('tab', { name })).toBeVisible()
  }
})

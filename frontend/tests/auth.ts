import { expect, type Page } from '@playwright/test'

export const API = process.env.FTM_TEST_API_URL ?? 'http://localhost:8000'
export const TEST_USER = { id: 'usr_test', username: 'tester', display_name: 'Test Farmer', created_at: '2026-11-14T00:00:00Z' }

/**
 * Mock a signed-in session (D14: every view needs an account). Unmocked API calls get 404, never a real 401,
 * so a test is not bounced to the sign-in page. Register this before the test's own routes: Playwright tries
 * the most recently added route first.
 */
export async function mockSignedIn(page: Page) {
  // Match on the path: a plain /api/ pattern would also catch Vite's own /src/api/*.ts modules.
  await page.route(
    (url) => url.pathname.startsWith('/api/'),
    (r) => r.fulfill({ status: 404, json: { detail: 'not mocked' } }),
  )
  await page.route(/\/api\/auth\/me$/, (r) => r.fulfill({ json: TEST_USER }))
  await page.route(/\/api\/health$/, (r) => r.fulfill({ json: { status: 'ok' } }))
  await page.route(/\/api\/sites\/[^/]+\/load$/, (r) =>
    r.fulfill({ json: { site_id: 'x', status: 'done', steps: [], has_strategies: false } }),
  )
}

/** Register a fresh account through the real sign-in page. */
export async function registerInUi(page: Page, prefix = 'e2e') {
  const username = `${prefix}-${Date.now()}`
  const password = 'an end to end test passphrase'
  await page.goto('/')
  await page.getByRole('radio', { name: 'Create account' }).click()
  await page.getByLabel('Your name').fill('E2E Farmer')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password').fill(password)
  await page.getByRole('button', { name: 'Create account', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'My farms' })).toBeVisible()
  return { username, password }
}

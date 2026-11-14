import { expect, test } from '@playwright/test'
import { API, mockSignedIn, registerInUi, TEST_USER } from './auth'

test('signed-out visitors only see the sign-in page', async ({ page }) => {
  await page.route(/\/api\/auth\/me$/, (r) => r.fulfill({ status: 401, json: { detail: 'Sign in to continue' } }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0)
  await page.getByRole('radio', { name: 'Create account' }).click()
  await page.getByLabel('Your name').fill('X')
  await page.getByLabel('Username').fill('someone')
  await page.getByLabel('Password', { exact: true }).fill('a long enough passphrase')
  await page.getByLabel('Confirm password').fill('a different passphrase!!')
  await page.getByRole('button', { name: 'Create account', exact: true }).last().click()
  await expect(page.getByRole('alert')).toHaveText('The two passwords do not match.')
})

test('an expired session returns to sign in with a notice', async ({ page }) => {
  await mockSignedIn(page)
  await page.route(/\/api\/sites(\?.*)?$/, (r) => r.fulfill({ status: 401, json: { detail: 'Sign in to continue' } }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.getByText('Your session has ended. Sign in again to continue.')).toBeVisible()
})

// Real account/session API; NASA/soil loading is covered in add-farm.spec.ts.
test('register, keep the session, update the profile, sign out and sign back in', async ({ page, request }) => {
  const health = await request.get(`${API}/health`).catch(() => null)
  test.skip(!health?.ok(), 'API not running')
  const { username, password } = await registerInUi(page, 'browser')
  await expect(page.getByText('Add your first farm')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'My farms' })).toBeVisible()
  await page.getByRole('button', { name: 'Your account' }).click()
  await page.getByLabel('Your name').fill('Updated Farmer')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Profile saved.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'My farms' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Your account' })).toContainText('Updated Farmer')
})

test('My farms lists, renames, archives and restores farms on one screen', async ({ page }) => {
  await mockSignedIn(page)
  let farm = { id: 'f1', owner_user_id: TEST_USER.id, name: 'North field', archived: false, latitude: 38, longitude: -100, timezone: 'UTC', area_ha: null, is_demo: false }
  await page.route(/\/api\/sites(\?.*)?$/, (r) =>
    r.fulfill({ json: new URL(r.request().url()).search || !farm.archived ? [farm] : [] }),
  )
  await page.route(/\/api\/sites\/f1$/, async (r) => {
    expect(r.request().method()).toBe('PUT')
    expect(r.request().headers()['x-ftm-request']).toBe('1')
    farm = { ...farm, ...r.request().postDataJSON() }
    return r.fulfill({ json: farm })
  })
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: 'Main' })
  await expect(nav.getByRole('button', { name: 'Add a farm' })).toHaveCount(0) // merged into My farms
  const card = page.getByRole('article', { name: 'North field' })
  await card.getByRole('button', { name: 'Rename' }).click()
  await page.getByLabel('Farm name', { exact: true }).fill('South field')
  await page.getByRole('button', { name: 'Save name' }).click()
  await expect(page.getByRole('heading', { name: 'South field' })).toBeVisible()
  await page.getByRole('article', { name: 'South field' }).getByRole('button', { name: 'Archive' }).click()
  await expect(page.getByText('Farm archived. Its data and decisions are kept.')).toBeVisible()
  await page.getByLabel('Show archived').check()
  await page.getByRole('article', { name: 'South field' }).getByRole('button', { name: 'Restore' }).click()
  await expect(page.getByRole('article', { name: 'South field' }).getByRole('button', { name: 'Open farm' })).toBeVisible()
  await page.getByRole('button', { name: '+ Add a farm' }).click()
  await expect(page.getByRole('heading', { name: /Add a farm: where is your field/ })).toBeVisible()
})

test("a new account's first farm keeps its load progress on screen until it can be opened", async ({ page }) => {
  await mockSignedIn(page)
  const farm = { id: 'new', owner_user_id: TEST_USER.id, name: 'First field', archived: false, latitude: -12.55, longitude: -55.72, timezone: 'UTC', area_ha: null, is_demo: false }
  const steps = (status: string) => [
    { name: 'weather', source: 'NASA POWER daily, 1981–2025', status },
    { name: 'soil', source: 'ISRIC SoilGrids 2.0', status: 'pending' },
    { name: 'vegetation', source: 'MODIS MOD13Q1 NDVI via Earth Engine', status: 'pending' },
  ]
  let created = false
  let polls = 0
  await page.route(/\/api\/sites(\?.*)?$/, (r) => {
    if (r.request().method() === 'POST') {
      created = true // the API stores the farm row as soon as loading starts
      return r.fulfill({ status: 202, json: { site_id: 'new', status: 'queued', steps: steps('pending'), has_strategies: false } })
    }
    return r.fulfill({ json: created ? [farm] : [] })
  })
  await page.route(/\/api\/sites\/new\/load$/, (r) => {
    polls += 1
    const done = polls > 1
    return r.fulfill({ json: { site_id: 'new', status: done ? 'done' : 'running', steps: steps(done ? 'done' : 'running'), has_strategies: false } })
  })
  await page.goto('/')
  await expect(page.getByText('Add your first farm')).toBeVisible()
  await page.getByLabel('Latitude').fill('-12.55')
  await page.getByLabel('Longitude').fill('-55.72')
  await page.getByLabel('Farm name').fill('First field')
  await page.getByRole('button', { name: 'Load this farm' }).click()
  await expect(page.getByRole('article', { name: 'First field' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /Loading data for First field/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open this farm' })).toBeVisible({ timeout: 15_000 })
})

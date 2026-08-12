import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { registerSession } from './helpers/session'

test.describe('Search namespace filter', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await setEnglishLocale(page)
    await registerSession(page, testInfo)
  })

  test('searches 125 namespace candidates and restores the selected URL filter', async ({ page }) => {
    const candidates = Array.from({ length: 125 }, (_, index) => ({
      slug: `team-${index + 1}`,
      displayName: `Team ${index + 1}`,
      visibleSkillCount: 125 - index,
    }))
    candidates[124] = { slug: 'foundation-models', displayName: 'AI Platform', visibleSkillCount: 7 }

    await page.route('**/api/web/search/namespaces**', async (route) => {
      const query = new URL(route.request().url()).searchParams.get('q')?.toLowerCase() ?? ''
      const filtered = query
        ? candidates.filter((item) => item.slug.includes(query) || item.displayName.toLowerCase().includes(query))
        : candidates.slice(0, 20)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: filtered.slice(0, 20) }),
      })
    })

    await page.goto('/')
    const filter = page.getByRole('button', { name: 'Filter by namespace' }).first()
    await filter.click()
    const namespaceInput = page.getByRole('textbox', { name: 'Search namespaces' })
    await namespaceInput.fill('FOUNDATION')
    await expect(page.getByRole('menuitem', { name: /AI Platform.*@foundation-models/ })).toBeVisible()
    await page.getByRole('menuitem', { name: /AI Platform.*@foundation-models/ }).click()

    await page.getByPlaceholder('Search skills...').fill('review')
    await page.getByRole('button', { name: 'Search', exact: true }).click()
    await expect(page).toHaveURL(/\/search\?/)
    expect(new URL(page.url()).searchParams.get('namespace')).toBe('foundation-models')
    expect(new URL(page.url()).searchParams.get('q')).toBe('review')
    await expect(page.getByRole('button', { name: 'Filter by namespace' })).toContainText('@foundation-models')

    await page.reload()
    await expect(page.getByRole('button', { name: 'Filter by namespace' })).toContainText('@foundation-models')

    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: 'Filter by namespace' }).click()
    const menuBox = await page.getByRole('menu').boundingBox()
    expect(menuBox).not.toBeNull()
    expect(menuBox!.x).toBeGreaterThanOrEqual(0)
    expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(390)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  })
})

test.describe('Anonymous landing namespace filter', () => {
  test('filters public namespaces without a session', async ({ page }) => {
    await setEnglishLocale(page)
    await page.route('**/api/web/search/namespaces**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: [{ slug: 'global', displayName: 'Global', visibleSkillCount: 10 }],
        }),
      })
    })

    await page.goto('/')
    await page.getByRole('button', { name: 'Filter by namespace' }).click()
    await page.getByRole('menuitem', { name: /Global.*@global/ }).click()
    await page.getByPlaceholder('Search skills...').fill('agent')
    await page.getByRole('button', { name: 'Search', exact: true }).click()

    await expect(page).toHaveURL(/\/search\?/)
    expect(new URL(page.url()).searchParams.get('namespace')).toBe('global')
    expect(new URL(page.url()).searchParams.get('q')).toBe('agent')

    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  })
})

import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'

test.describe('Light and dark theme', () => {
  test.beforeEach(async ({ page }) => {
    await setEnglishLocale(page)
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: {
            userId: 'theme-layout-user',
            displayName: 'Theme User',
            platformRoles: [],
            oauthProvider: 'local',
            canChangePassword: true,
          },
          timestamp: '2026-09-06T00:00:00Z',
          requestId: 'theme-auth-fixture',
        }),
      })
    })
    await page.route('**/api/web/me/namespaces', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        code: 0, msg: 'success', data: [], timestamp: '2026-09-06T00:00:00Z', requestId: 'theme-namespaces-fixture',
      }) })
    })
    await page.route('**/api/web/notifications/unread-count', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        code: 0, msg: 'success', data: { count: 0 }, timestamp: '2026-09-06T00:00:00Z', requestId: 'theme-notifications-fixture',
      }) })
    })
    await page.route('**/api/web/notifications/sse', async (route) => {
      await route.fulfill({ status: 204 })
    })
    await page.route('**/api/web/skills?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: { items: [], total: 0, page: 0, size: 6 },
          timestamp: '2026-09-06T00:00:00Z',
          requestId: 'theme-skills-fixture',
        }),
      })
    })
    await page.addInitScript(() => {
      const observedWindow = window as Window & { __themeAtFirstReactContent?: boolean }
      const observer = new MutationObserver(() => {
        const root = document.querySelector('#root')
        if (root?.childElementCount) {
          observedWindow.__themeAtFirstReactContent = document.documentElement.classList.contains('dark')
          observer.disconnect()
        }
      })
      observer.observe(document, { childList: true, subtree: true })
      if (!window.sessionStorage.getItem('theme-test-initialized')) {
        window.localStorage.removeItem('skillhub-theme')
        window.sessionStorage.setItem('theme-test-initialized', 'true')
      }
    })
  })

  test('persists the selection before React renders and fits a narrow header', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.stack ?? error.message))
    await page.goto('/')
    await expect.poll(() => pageErrors).toEqual([])
    await expect(page.locator('html')).not.toHaveClass(/dark/)

    const themeSwitch = page.getByRole('switch', { name: 'Dark theme' })
    await expect(themeSwitch).toHaveAttribute('aria-checked', 'false')
    await themeSwitch.click()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect.poll(() => page.evaluate(() => window.localStorage.getItem('skillhub-theme'))).toBe('dark')

    await page.reload()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect.poll(() => page.evaluate(() => (
      window as Window & { __themeAtFirstReactContent?: boolean }
    ).__themeAtFirstReactContent)).toBe(true)

    await page.setViewportSize({ width: 320, height: 568 })
    await expect(page.getByRole('switch', { name: 'Dark theme' })).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
})

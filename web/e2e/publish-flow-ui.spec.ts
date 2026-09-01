import { expect, test } from '@playwright/test'
import path from 'node:path'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { registerSession } from './helpers/session'
import { E2eTestDataBuilder } from './helpers/test-data-builder'

interface PublishEnvelope {
  code: number
  msg?: string
  data: {
    namespace: string
    slug: string
    version: string
  }
}

test.describe('Publish Flow UI (Real API)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await setEnglishLocale(page)
    await registerSession(page, testInfo)
  })

  test('publishes a generated skill package from dashboard page', async ({ page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()

    try {
      const namespace = await builder.ensureWritableNamespace()
      const skillName = `publish-ui-${Date.now().toString(36)}`
      const packagePath = builder.createSkillPackageFile({ name: skillName })

      await page.goto('/dashboard/publish')
      await expect(page.getByRole('heading', { name: 'Publish Skill' })).toBeVisible()

      const namespaceTrigger = page.locator('#namespace')
      await expect(namespaceTrigger).toBeVisible()
      await namespaceTrigger.click()
      const namespaceSearch = page.getByRole('searchbox', { name: 'Search namespaces' })
      await expect(namespaceSearch).toBeFocused()
      await namespaceSearch.fill(namespace.slug)
      const namespaceOption = page.getByRole('menuitem', {
        name: new RegExp(`@${namespace.slug}`),
      }).first()
      await expect(namespaceOption).toBeVisible()
      await namespaceOption.click()
      await expect(namespaceTrigger).toContainText(`@${namespace.slug}`)

      await page.locator('input[type="file"][accept*=".zip"]').setInputFiles(packagePath)
      await expect(page.getByText(path.basename(packagePath))).toBeVisible()
      const confirmButton = page.getByRole('button', { name: 'Confirm Publish' })
      await expect(confirmButton).toBeEnabled()
      const publishResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST'
          && response.url().includes(`/api/web/skills/${encodeURIComponent(namespace.slug)}/publish`),
        { timeout: 90_000 },
      )
      await confirmButton.click()
      const publishResponse = await publishResponsePromise
      const publishBody = await publishResponse.json() as PublishEnvelope

      expect(publishResponse.status(), `publish failed: ${publishBody.msg ?? 'unknown error'}`).toBe(200)
      expect(publishBody.code).toBe(0)
      expect(publishBody.data.namespace).toBe(namespace.slug)

      await page.goto('/dashboard/skills')
      await expect(page.getByRole('heading', { name: 'My Skills' })).toBeVisible({ timeout: 30_000 })
      await expect(page.getByRole('heading', { name: skillName, exact: true })).toBeVisible({ timeout: 30_000 })
      await expect(page.getByText(`@${publishBody.data.namespace}`).first()).toBeVisible()
      await expect(page.getByText(`v${publishBody.data.version}`).first()).toBeVisible()
    } finally {
      await builder.cleanup()
    }
  })

  test('searches 125 namespaces without overflowing desktop or mobile viewports', async ({ page }) => {
    const namespaces = Array.from({ length: 125 }, (_, index) => ({
      id: index + 1,
      slug: `team-${index + 1}`,
      displayName: `Team ${index + 1}`,
      type: 'TEAM',
      status: 'ACTIVE',
      createdAt: '2026-08-12T00:00:00Z',
      immutable: false,
      canFreeze: false,
      canUnfreeze: false,
      canArchive: false,
      canRestore: false,
      canDelete: false,
    }))
    namespaces[124] = {
      ...namespaces[124],
      slug: 'foundation-models',
      displayName: 'AI Platform',
    }

    await page.route('**/api/web/me/namespaces', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: namespaces }),
      })
    })

    await page.goto('/dashboard/publish')
    const namespaceTrigger = page.locator('#namespace')
    await namespaceTrigger.click()

    const namespaceMenu = page.getByRole('menu')
    const scrollArea = namespaceMenu.locator('.max-h-80')
    await expect(scrollArea).toBeVisible()
    expect(await scrollArea.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true)

    const namespaceSearch = page.getByRole('searchbox', { name: 'Search namespaces' })
    await namespaceSearch.fill('FOUNDATION-models')
    await expect(page.getByRole('menuitem', { name: /AI Platform.*@foundation-models/ })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: /Team 1.*@team-1/ })).toHaveCount(0)
    await page.getByRole('menuitem', { name: /AI Platform.*@foundation-models/ }).click()
    await expect(namespaceTrigger).toContainText('AI Platform (@foundation-models)')

    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await namespaceTrigger.click()
    await page.getByRole('searchbox', { name: 'Search namespaces' }).fill('AI PLATFORM')
    const mobileMenuBox = await page.getByRole('menu').boundingBox()
    expect(mobileMenuBox).not.toBeNull()
    expect(mobileMenuBox!.x).toBeGreaterThanOrEqual(0)
    expect(mobileMenuBox!.x + mobileMenuBox!.width).toBeLessThanOrEqual(390)
    await page.getByRole('menuitem', { name: /AI Platform.*@foundation-models/ }).click()
    const mobileTriggerBox = await namespaceTrigger.boundingBox()
    expect(mobileTriggerBox).not.toBeNull()
    expect(mobileTriggerBox!.x + mobileTriggerBox!.width).toBeLessThanOrEqual(390)
  })
})

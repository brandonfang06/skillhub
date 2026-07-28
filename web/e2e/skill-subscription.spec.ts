import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { loginWithCredentials, registerSession } from './helpers/session'
import { E2eTestDataBuilder } from './helpers/test-data-builder'

function getOptionalEnv(name: string): string | undefined {
  const value = process.env[name]?.trim()
  return value ? value : undefined
}

function adminCredentials() {
  return {
    username: getOptionalEnv('E2E_ADMIN_USERNAME') ?? getOptionalEnv('BOOTSTRAP_ADMIN_USERNAME') ?? 'admin',
    password: getOptionalEnv('E2E_ADMIN_PASSWORD') ?? getOptionalEnv('BOOTSTRAP_ADMIN_PASSWORD') ?? 'ChangeMe!2026',
  }
}

test.describe('Skill Subscription (Real API)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await setEnglishLocale(page)
    await registerSession(page, testInfo)
  })

  test('subscribe and unsubscribe to a skill', async ({ page, browser }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()

    const adminContext = await browser.newContext()
    const adminPage = await adminContext.newPage()
    const adminBuilder = new E2eTestDataBuilder(adminPage, testInfo)
    await loginWithCredentials(adminPage, adminCredentials(), testInfo)
    await adminBuilder.init()

    try {
      const namespace = await builder.ensureWritableNamespace()
      const skill = await builder.publishSkill(namespace.slug)

      const reviewTaskId = await adminBuilder.waitForPendingReview(namespace.slug, skill.slug, skill.version)
      await adminBuilder.approveReview(reviewTaskId)

      await page.goto(`/space/${namespace.slug}/${skill.slug}`)

      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()

      const subscribeButton = page.getByRole('button', { name: /^Subscribe \(\d+\)$/ })
      await expect(subscribeButton).toBeVisible()

      const subscribeResponsePromise = page.waitForResponse((response) =>
        response.request().method() === 'PUT'
        && /\/api\/web\/skills\/\d+\/subscription$/.test(new URL(response.url()).pathname),
      )
      await subscribeButton.click()
      expect((await subscribeResponsePromise).ok()).toBeTruthy()

      await expect(page.getByRole('button', { name: /^Subscribed \(\d+\)$/ })).toBeVisible()

      const subscribedButton = page.getByRole('button', { name: /^Subscribed \(\d+\)$/ })
      const unsubscribeResponsePromise = page.waitForResponse((response) =>
        response.request().method() === 'DELETE'
        && /\/api\/web\/skills\/\d+\/subscription$/.test(new URL(response.url()).pathname),
      )
      await subscribedButton.click()
      expect((await unsubscribeResponsePromise).ok()).toBeTruthy()

      await expect(page.getByRole('button', { name: /^Subscribe \(\d+\)$/ })).toBeVisible()
    } finally {
      await adminBuilder.cleanup()
      await adminContext.close()
      await builder.cleanup()
    }
  })

  test('shows subscribed skill in My Subscriptions page', async ({ page, browser }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()

    const adminContext = await browser.newContext()
    const adminPage = await adminContext.newPage()
    const adminBuilder = new E2eTestDataBuilder(adminPage, testInfo)
    await loginWithCredentials(adminPage, adminCredentials(), testInfo)
    await adminBuilder.init()

    try {
      const namespace = await builder.ensureWritableNamespace()
      const skill = await builder.publishSkill(namespace.slug)

      const reviewTaskId = await adminBuilder.waitForPendingReview(namespace.slug, skill.slug, skill.version)
      await adminBuilder.approveReview(reviewTaskId)

      await page.goto(`/space/${namespace.slug}/${skill.slug}`)

      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()

      const subscribeButton = page.getByRole('button', { name: /^Subscribe \(\d+\)$/ })
      await expect(subscribeButton).toBeVisible()
      const subscribeResponsePromise = page.waitForResponse((response) =>
        response.request().method() === 'PUT'
        && /\/api\/web\/skills\/\d+\/subscription$/.test(new URL(response.url()).pathname),
      )
      await subscribeButton.click()
      expect((await subscribeResponsePromise).ok()).toBeTruthy()

      await expect(page.getByRole('button', { name: /^Subscribed \(\d+\)$/ })).toBeVisible()

      await page.goto('/dashboard/subscriptions')

      await expect(page.getByRole('heading', { name: 'My Subscriptions' })).toBeVisible()
      await expect(page.getByText(`@${skill.namespace}`).first()).toBeVisible()
    } finally {
      await adminBuilder.cleanup()
      await adminContext.close()
      await builder.cleanup()
    }
  })
})

import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { createFreshSession, loginWithCredentials, registerSession } from './helpers/session'
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

      const subscribeButton = page.getByRole('button', { name: /Subscribe/ })
      await expect(subscribeButton).toBeVisible()

      await subscribeButton.click()

      await expect(page.getByRole('button', { name: /Subscribed/ })).toBeVisible()

      const subscribedButton = page.getByRole('button', { name: /Subscribed/ })
      await subscribedButton.click()

      await expect(page.getByRole('button', { name: /Subscribe/ })).toBeVisible()
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

      const subscribeButton = page.getByRole('button', { name: /Subscribe/ })
      await expect(subscribeButton).toBeVisible()
      await subscribeButton.click()

      await expect(page.getByRole('button', { name: /Subscribed/ })).toBeVisible()

      await page.goto('/dashboard/subscriptions')

      await expect(page.getByRole('heading', { name: 'My Subscriptions' })).toBeVisible()
      await expect(page.getByText(`@${skill.namespace}`).first()).toBeVisible()
    } finally {
      await adminBuilder.cleanup()
      await adminContext.close()
      await builder.cleanup()
    }
  })

  test('receives a live and durable notification when a subscribed skill publishes a new version', async ({ page, browser }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()

    const adminContext = await browser.newContext()
    const adminPage = await adminContext.newPage()
    const adminBuilder = new E2eTestDataBuilder(adminPage, testInfo)
    await loginWithCredentials(adminPage, adminCredentials(), testInfo)
    await adminBuilder.init()

    const subscriberContext = await browser.newContext()
    const subscriberPage = await subscriberContext.newPage()
    const subscriberBuilder = new E2eTestDataBuilder(subscriberPage, testInfo)
    await setEnglishLocale(subscriberPage)
    await createFreshSession(subscriberPage, testInfo)
    await subscriberBuilder.init()

    try {
      const namespace = await builder.ensureWritableNamespace()
      const skillName = `subscription-notification-${Date.now().toString(36)}`
      const firstVersion = await builder.publishSkill(namespace.slug, {
        name: skillName,
        version: '1.0.0',
      })
      const firstReviewTaskId = await adminBuilder.waitForPendingReview(
        namespace.slug,
        firstVersion.slug,
        firstVersion.version,
      )
      await adminBuilder.approveReview(firstReviewTaskId)

      const sseRequest = subscriberPage.waitForRequest((request) => (
        new URL(request.url()).pathname.endsWith('/api/web/notifications/sse')
      ))
      await subscriberPage.goto(
        `/space/${encodeURIComponent(namespace.slug)}/${encodeURIComponent(firstVersion.slug)}`,
      )
      await sseRequest
      await subscriberPage.getByRole('button', { name: /Subscribe/ }).click()
      await expect(subscriberPage.getByRole('button', { name: /Subscribed/ })).toBeVisible()

      const markReadResponse = await subscriberPage.context().request.put(
        '/api/web/notifications/read-all',
      )
      expect(markReadResponse.ok()).toBe(true)

      const secondVersion = await builder.publishSkill(namespace.slug, {
        name: skillName,
        version: '1.1.0',
      })
      const secondReviewTaskId = await adminBuilder.waitForPendingReview(
        namespace.slug,
        secondVersion.slug,
        secondVersion.version,
      )
      await adminBuilder.approveReview(secondReviewTaskId)

      await expect(subscriberPage.getByLabel('1 unread')).toBeVisible()
      await subscriberPage.reload()
      await expect(subscriberPage.getByLabel('1 unread')).toBeVisible()

      await subscriberPage.getByRole('button', { name: 'Notifications' }).click()
      const notificationTitle = subscriberPage.getByText('Subscribed skill updated').first()
      await expect(notificationTitle).toBeVisible()
      await expect(
        subscriberPage.getByText(`${skillName} (1.1.0) published a new version.`).first(),
      ).toBeVisible()
      await notificationTitle.click()
      await expect(subscriberPage).toHaveURL(
        new RegExp(`/space/${namespace.slug}/${firstVersion.slug}$`),
      )

      const clearResponse = await subscriberPage.context().request.put(
        '/api/web/notifications/read-all',
      )
      expect(clearResponse.ok()).toBe(true)
      await subscriberPage.goto('/settings/notifications')
      const publishToggle = subscriberPage.getByRole('switch', {
        name: 'Publish Notifications',
      })
      await expect(publishToggle).toHaveAttribute('aria-checked', 'true')
      const preferenceResponse = subscriberPage.waitForResponse((response) => (
        new URL(response.url()).pathname.endsWith('/api/web/notification-preferences')
        && response.request().method() === 'PUT'
      ))
      await publishToggle.click()
      expect((await preferenceResponse).ok()).toBe(true)
      await expect(publishToggle).toHaveAttribute('aria-checked', 'false')

      const thirdVersion = await builder.publishSkill(namespace.slug, {
        name: skillName,
        version: '1.2.0',
      })
      const thirdReviewTaskId = await adminBuilder.waitForPendingReview(
        namespace.slug,
        thirdVersion.slug,
        thirdVersion.version,
      )
      await adminBuilder.approveReview(thirdReviewTaskId)

      const publishNotifications = await subscriberPage.context().request.get(
        '/api/web/notifications?category=PUBLISH&page=0&size=100',
      )
      expect(publishNotifications.ok()).toBe(true)
      const publishBody = await publishNotifications.json() as {
        data: { items: Array<{ bodyJson?: string }> }
      }
      expect(publishBody.data.items.some((item) => (
        item.bodyJson?.includes('"version":"1.2.0"')
      ))).toBe(false)
      const unreadResponse = await subscriberPage.context().request.get(
        '/api/web/notifications/unread-count',
      )
      expect(unreadResponse.ok()).toBe(true)
      expect((await unreadResponse.json() as { data: { count: number } }).data.count).toBe(0)
    } finally {
      await subscriberBuilder.cleanup()
      await subscriberContext.close()
      await adminBuilder.cleanup()
      await adminContext.close()
      await builder.cleanup()
    }
  })
})

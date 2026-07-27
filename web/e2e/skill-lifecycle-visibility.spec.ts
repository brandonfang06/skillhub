import path from 'node:path'
import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
  type TestInfo,
} from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import {
  createFreshSession,
  loginWithCredentials,
  registerSession,
} from './helpers/session'
import {
  E2eTestDataBuilder,
  type SeededNamespace,
} from './helpers/test-data-builder'

interface ApiEnvelope<T> {
  code: number
  data: T
  detail?: string
  msg?: string
}

interface ReviewableNamespaceSetup {
  adminBuilder: E2eTestDataBuilder
  adminContext: BrowserContext
  adminPage: Page
  namespace: SeededNamespace
}

async function prepareReviewableNamespace(
  browser: Browser,
  ownerPage: Page,
  testInfo: TestInfo,
): Promise<ReviewableNamespaceSetup> {
  const adminContext = await browser.newContext({
    baseURL: String(testInfo.project.use.baseURL),
  })
  const adminPage = await adminContext.newPage()
  await setEnglishLocale(adminPage)
  await loginWithCredentials(
    adminPage,
    { username: 'admin', password: 'ChangeMe!2026' },
    testInfo,
  )

  const adminBuilder = new E2eTestDataBuilder(adminPage, testInfo)
  await adminBuilder.init()
  const namespace = await adminBuilder.createNamespace('e2e-lifecycle')

  const meResponse = await ownerPage.context().request.get('/api/v1/auth/me')
  const meBody = await meResponse.json() as ApiEnvelope<{ userId: string }>
  expect(meResponse.status(), meBody.detail || meBody.msg || 'owner session lookup failed').toBe(200)
  await adminBuilder.addNamespaceMember(namespace.slug, meBody.data.userId, 'MEMBER')

  return {
    adminBuilder,
    adminContext,
    adminPage,
    namespace,
  }
}

async function decideReviewAsAdmin(
  page: Page,
  reviewTaskId: number,
  decision: 'approve' | 'reject',
): Promise<void> {
  const response = await page.context().request.post(
    `/api/web/reviews/${reviewTaskId}/${decision}`,
    {
      data: {
        comment: `${decision} by lifecycle visibility E2E`,
      },
    },
  )
  const body = await response.json() as ApiEnvelope<unknown>
  expect(response.status(), body.detail || body.msg || `review ${decision} failed`).toBe(200)
  expect(body.code).toBe(0)
}

async function selectPublishNamespace(page: Page, namespaceSlug: string): Promise<void> {
  const trigger = page.locator('#namespace')
  await trigger.click()
  const option = page.getByRole('option', {
    name: new RegExp(`\\(@${namespaceSlug}\\)`),
  }).first()
  await expect(option).toBeVisible()
  await option.click()
  await expect(trigger).toContainText(`@${namespaceSlug}`)
}

async function changeVisibility(page: Page, label: string): Promise<void> {
  const trigger = page.getByRole('combobox', { name: 'Skill visibility' })
  await trigger.click()
  await page.getByRole('option', { name: label, exact: true }).click()
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'PATCH'
      && response.url().includes('/visibility'),
  )
  await page.getByRole('button', { name: 'Save visibility' }).click()
  const response = await responsePromise
  expect(response.status()).toBe(200)
  await expect(page.getByText('Visibility updated')).toBeVisible()
}

test.describe('Rejected publish and lifecycle visibility (Real API)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await setEnglishLocale(page)
    await registerSession(page, testInfo)
  })

  test('shows dedicated guidance when a rejected version is uploaded again', async ({ browser, page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()
    let setup: ReviewableNamespaceSetup | null = null

    try {
      setup = await prepareReviewableNamespace(browser, page, testInfo)
      const { adminPage, namespace } = setup
      const skillName = `rejected-reuse-${Date.now().toString(36)}`
      const skill = await builder.publishSkill(namespace.slug, {
        name: skillName,
        version: '0.1.0',
      })
      const reviewTaskId = await setup.adminBuilder.waitForPendingReview(
        namespace.slug,
        skill.slug,
        skill.version,
      )
      await setup.adminBuilder.waitForReviewScanReady(reviewTaskId)
      await decideReviewAsAdmin(adminPage, reviewTaskId, 'reject')

      const packagePath = builder.createSkillPackageFile({
        name: skillName,
        description: 'Updated after review but still using the rejected version',
        version: '0.1.0',
      })
      await page.goto('/dashboard/publish')
      await selectPublishNamespace(page, namespace.slug)
      await page.locator('input[type="file"]').setInputFiles(packagePath)
      await expect(page.getByText(path.basename(packagePath))).toBeVisible()

      const responsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST'
          && response.url().includes(`/api/web/skills/${encodeURIComponent(namespace.slug)}/publish`),
      )
      await page.getByRole('button', { name: 'Confirm Publish' }).click()
      const response = await responsePromise

      expect(response.status()).toBe(409)
      await expect(page.getByText('Unable to reuse rejected version')).toBeVisible()
      await expect(page.getByText(/Update the skill based on the review result/)).toBeVisible()
      await expect(page.getByText('Publish Failed')).toHaveCount(0)

      const historyResponse = await adminPage.context().request.get(`/api/web/reviews/${reviewTaskId}`)
      const historyBody = await historyResponse.json() as ApiEnvelope<{
        reviewComment: string
        status: string
        versionStatus: string
      }>
      expect(historyResponse.status()).toBe(200)
      expect(historyBody.data.status).toBe('REJECTED')
      expect(historyBody.data.versionStatus).toBe('REJECTED')
      expect(historyBody.data.reviewComment).toContain('reject by lifecycle visibility E2E')
    } finally {
      await builder.cleanup()
      await setup?.adminBuilder.cleanup()
      await setup?.adminContext.close()
    }
  })

  test('keeps visibility editing manager-only across desktop and mobile viewports', async ({ browser, page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()
    let memberContext: Awaited<ReturnType<typeof browser.newContext>> | null = null
    let setup: ReviewableNamespaceSetup | null = null

    try {
      setup = await prepareReviewableNamespace(browser, page, testInfo)
      const { adminPage, namespace } = setup
      const skillName = `visibility-${Date.now().toString(36)}`
      const skill = await builder.publishSkill(namespace.slug, { name: skillName })
      const reviewTaskId = await setup.adminBuilder.waitForPendingReview(
        namespace.slug,
        skill.slug,
        skill.version,
      )
      await setup.adminBuilder.waitForReviewScanReady(reviewTaskId)
      await decideReviewAsAdmin(adminPage, reviewTaskId, 'approve')

      memberContext = await browser.newContext({ baseURL: String(testInfo.project.use.baseURL) })
      const memberPage = await memberContext.newPage()
      await setEnglishLocale(memberPage)
      await createFreshSession(memberPage, testInfo)
      const meResponse = await memberPage.context().request.get('/api/v1/auth/me')
      const meBody = await meResponse.json() as ApiEnvelope<{ userId: string }>
      expect(meResponse.status()).toBe(200)
      await setup.adminBuilder.addNamespaceMember(namespace.slug, meBody.data.userId, 'MEMBER')

      await page.setViewportSize({ width: 1440, height: 900 })
      await page.goto(`/space/${namespace.slug}/${skill.slug}`)
      await expect(page.getByRole('heading', { name: skillName }).first()).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'Skill visibility' })).toContainText('Public')
      await changeVisibility(page, 'Private')
      await expect(page.getByRole('combobox', { name: 'Skill visibility' })).toContainText('Private')

      const privateDetailResponse = await memberPage.context().request.get(
        `/api/web/skills/${encodeURIComponent(namespace.slug)}/${encodeURIComponent(skill.slug)}`,
      )
      expect(privateDetailResponse.status()).toBe(403)
      const privateSearchResponse = await memberPage.context().request.get(
        `/api/web/skills?q=${encodeURIComponent(skillName)}&sort=relevance&page=0&size=50`,
      )
      const privateSearchBody = await privateSearchResponse.json() as ApiEnvelope<{
        items: Array<{ slug: string }>
      }>
      expect(privateSearchResponse.status()).toBe(200)
      expect(privateSearchBody.data.items.map((item) => item.slug)).not.toContain(skill.slug)

      await page.setViewportSize({ width: 390, height: 844 })
      await page.reload()
      await expect(page.getByRole('combobox', { name: 'Skill visibility' })).toContainText('Private')
      await changeVisibility(page, 'Namespace Only')
      await expect(page.getByRole('combobox', { name: 'Skill visibility' })).toContainText('Namespace Only')

      await memberPage.setViewportSize({ width: 390, height: 844 })
      await memberPage.goto(`/space/${namespace.slug}/${skill.slug}`)
      await expect(memberPage.getByRole('heading', { name: skillName }).first()).toBeVisible()
      await expect(memberPage.getByText('Namespace Only', { exact: true }).first()).toBeVisible()
      await expect(memberPage.getByRole('combobox', { name: 'Skill visibility' })).toHaveCount(0)
      await expect(memberPage.getByRole('button', { name: 'Save visibility' })).toHaveCount(0)
    } finally {
      await memberContext?.close()
      await builder.cleanup()
      await setup?.adminBuilder.cleanup()
      await setup?.adminContext.close()
    }
  })

  test('keeps a newer manual visibility change when a pending review is approved', async ({ browser, page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()
    let setup: ReviewableNamespaceSetup | null = null

    try {
      setup = await prepareReviewableNamespace(browser, page, testInfo)
      const { adminPage, namespace } = setup
      const skillName = `pending-visibility-${Date.now().toString(36)}`
      const firstVersion = await builder.publishSkill(namespace.slug, {
        name: skillName,
        version: '1.0.0',
      })
      const firstReviewId = await setup.adminBuilder.waitForPendingReview(
        namespace.slug,
        firstVersion.slug,
        firstVersion.version,
      )
      await setup.adminBuilder.waitForReviewScanReady(firstReviewId)
      await decideReviewAsAdmin(adminPage, firstReviewId, 'approve')

      const secondVersion = await builder.publishSkill(namespace.slug, {
        name: skillName,
        version: '2.0.0',
      })
      const secondReviewId = await setup.adminBuilder.waitForPendingReview(
        namespace.slug,
        secondVersion.slug,
        secondVersion.version,
      )
      await setup.adminBuilder.waitForReviewScanReady(secondReviewId)

      await page.goto(`/space/${namespace.slug}/${secondVersion.slug}`)
      await changeVisibility(page, 'Private')
      await decideReviewAsAdmin(adminPage, secondReviewId, 'approve')
      await page.reload()

      await expect(page.getByRole('combobox', { name: 'Skill visibility' })).toContainText('Private')
      const detailResponse = await page.context().request.get(
        `/api/web/skills/${encodeURIComponent(namespace.slug)}/${encodeURIComponent(secondVersion.slug)}`,
      )
      const detailBody = await detailResponse.json() as ApiEnvelope<{
        publishedVersion?: { version: string }
        visibility: string
      }>
      expect(detailResponse.status()).toBe(200)
      expect(detailBody.data.visibility).toBe('PRIVATE')
      expect(detailBody.data.publishedVersion?.version).toBe('2.0.0')
    } finally {
      await builder.cleanup()
      await setup?.adminBuilder.cleanup()
      await setup?.adminContext.close()
    }
  })

  test('keeps an older published version searchable when the latest owner preview is private', async ({ browser, page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()
    let anonymousContext: BrowserContext | null = null
    let setup: ReviewableNamespaceSetup | null = null

    try {
      setup = await prepareReviewableNamespace(browser, page, testInfo)
      const { adminPage, namespace } = setup
      const skillName = `published-fallback-${Date.now().toString(36)}`
      const firstVersion = await builder.publishSkill(namespace.slug, {
        name: skillName,
        version: '1.0.0',
      })
      const firstReviewId = await setup.adminBuilder.waitForPendingReview(
        namespace.slug,
        firstVersion.slug,
        firstVersion.version,
      )
      await setup.adminBuilder.waitForReviewScanReady(firstReviewId)
      await decideReviewAsAdmin(adminPage, firstReviewId, 'approve')

      await builder.publishSkill(namespace.slug, {
        name: skillName,
        version: '2.0.0',
        visibility: 'PRIVATE',
      })
      await page.goto(`/space/${namespace.slug}/${firstVersion.slug}`)
      await expect(page.getByRole('combobox', { name: 'Skill visibility' })).toContainText('Private')
      await changeVisibility(page, 'Public')

      anonymousContext = await browser.newContext({ baseURL: String(testInfo.project.use.baseURL) })
      const searchResponse = await anonymousContext.request.get(
        `/api/web/skills?q=${encodeURIComponent(skillName)}&sort=relevance&page=0&size=50`,
      )
      const searchBody = await searchResponse.json() as ApiEnvelope<{
        items: Array<{
          headlineVersion?: { version: string }
          slug: string
        }>
      }>
      expect(searchResponse.status()).toBe(200)
      const searchResult = searchBody.data.items.find((item) => item.slug === firstVersion.slug)
      expect(searchResult).toBeDefined()
      expect(searchResult?.headlineVersion?.version).toBe('1.0.0')
    } finally {
      await anonymousContext?.close()
      await builder.cleanup()
      await setup?.adminBuilder.cleanup()
      await setup?.adminContext.close()
    }
  })

  test('rejects visibility changes after the namespace is archived', async ({ browser, page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()
    let setup: ReviewableNamespaceSetup | null = null

    try {
      setup = await prepareReviewableNamespace(browser, page, testInfo)
      const { adminPage, namespace } = setup
      const skill = await builder.publishSkill(namespace.slug, {
        name: `archived-visibility-${Date.now().toString(36)}`,
        visibility: 'PRIVATE',
      })
      const archiveResponse = await adminPage.context().request.post(
        `/api/web/namespaces/${encodeURIComponent(namespace.slug)}/archive`,
        { data: { reason: 'visibility lifecycle E2E' } },
      )
      expect(archiveResponse.status()).toBe(200)

      const visibilityResponse = await page.context().request.patch(
        `/api/web/skills/${encodeURIComponent(namespace.slug)}/${encodeURIComponent(skill.slug)}/visibility`,
        { data: { visibility: 'PUBLIC' } },
      )
      const visibilityBody = await visibilityResponse.json() as ApiEnvelope<unknown>
      expect(visibilityResponse.status()).toBe(400)
      expect(visibilityBody.detail).toBe('error.namespace.archived')
    } finally {
      await builder.cleanup()
      await setup?.adminBuilder.cleanup()
      await setup?.adminContext.close()
    }
  })
})

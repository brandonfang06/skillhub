import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { createNamespaceReviewData } from './helpers/review-seed'

test.describe('Review requested visibility (Real API)', () => {
  test.describe.configure({ timeout: 120_000 })

  test('shows the submitted visibility to a namespace reviewer on desktop and mobile', async ({ browser, page }, testInfo) => {
    await setEnglishLocale(page)
    let seeded: Awaited<ReturnType<typeof createNamespaceReviewData>> | undefined

    try {
      seeded = await createNamespaceReviewData(browser, page, testInfo, {
        visibility: 'NAMESPACE_ONLY',
      })

      const visibilityResponse = await page.context().request.patch(
        `/api/web/skills/${encodeURIComponent(seeded.namespace.slug)}/${encodeURIComponent(seeded.skill.slug)}/visibility`,
        { data: { visibility: 'PRIVATE' } },
      )
      expect(visibilityResponse.status()).toBe(200)

      const [reviewerResponse, reviewResponse] = await Promise.all([
        page.context().request.get('/api/v1/auth/me'),
        page.context().request.get(`/api/web/reviews/${seeded.reviewTaskId}`),
      ])
      expect(reviewerResponse.status()).toBe(200)
      expect(reviewResponse.status()).toBe(200)
      const reviewer = await reviewerResponse.json() as { data: { userId: string } }
      const review = await reviewResponse.json() as {
        data: {
          approvalVisibility: string
          requestedVisibility: string
          submittedBy: string
        }
      }
      expect(review.data.submittedBy).not.toBe(reviewer.data.userId)
      expect(review.data.requestedVisibility).toBe('NAMESPACE_ONLY')
      expect(review.data.approvalVisibility).toBe('PRIVATE')

      for (const viewport of [
        { width: 1280, height: 720 },
        { width: 390, height: 844 },
      ]) {
        await page.setViewportSize(viewport)
        await page.goto(
          `/dashboard/namespaces/${seeded.namespace.slug}/reviews/${seeded.reviewTaskId}`,
        )

        const label = page.getByText('Requested visibility', { exact: true })
        await expect(label).toBeVisible()
        const visibilityField = label.locator('..')
        await expect(visibilityField.getByText('Namespace Only', { exact: true })).toBeVisible()
        await expect(page.getByText('Approval visibility', { exact: true })).toBeVisible()
        await expect(page.getByText('Private', { exact: true })).toBeVisible()
        await expect(page.getByText('Visibility changed after submission. Approval will use this value.')).toBeVisible()
        await expect(page.getByRole('button', { name: 'Approve' })).toBeVisible()
        await expect(page.getByRole('button', { name: 'Reject' })).toBeVisible()
        expect(
          await visibilityField.evaluate((element) => element.scrollWidth <= element.clientWidth),
        ).toBe(true)
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
        ).toBe(true)
      }
    } finally {
      await seeded?.cleanup()
    }
  })
})

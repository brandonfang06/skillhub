import { expect, test } from '@playwright/test'

const suffix = process.env.REVIEW_SMOKE_SUFFIX
test.skip(!suffix, 'Requires the disposable real-service review-context smoke fixtures')

for (const base of ['http://127.0.0.1:58180', 'http://127.0.0.1:58182/skillhub']) {
  for (const width of [1440, 390]) {
    test(`namespace reviewers ${base} ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 })
      await page.addInitScript(() => localStorage.setItem('i18nextLng', 'zh-TW'))
      const errors: string[] = []
      const failedResponses: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      page.on('response', (response) => {
        if (response.status() >= 400 && response.url().includes('/api/')) failedResponses.push(`${response.status()} ${response.url()}`)
      })
      const login = await page.request.post(`${base}/api/v1/auth/local/login`, {
        data: { username: `rc_publisher_${suffix}`, password: 'ReviewSmoke123!' },
      })
      expect(login.ok()).toBeTruthy()
      await page.goto(`${base}/space/review-smoke-${suffix}/reviewer-flow`)
      const toggle = page.getByRole('button', { name: /Namespace 可審核人員/ })
      await expect(toggle).toBeVisible()
      await expect(toggle).toContainText('3.0.0')
      await expect(toggle).toHaveAttribute('aria-expanded', 'true')
      const card = toggle.locator('..')
      await expect(card.getByText('Namespace ADMIN：7 人')).toBeVisible()
      await expect(card.getByText('Review Admin 1', { exact: true })).toBeVisible()
      await expect(card.getByText(`rc_reviewer_${suffix}`, { exact: true })).toBeVisible()
      await card.getByRole('button', { name: '下一頁', exact: true }).click()
      await expect(card.getByText('Review Admin 6', { exact: true })).toBeVisible()
      await expect(card.getByRole('button', { name: '下一頁', exact: true })).toBeDisabled()
      await page.screenshot({ path: testInfo.outputPath('detail.png'), fullPage: true })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
      await page.goto(`${base}/dashboard/review-progress`)
      const article = page.locator('article').filter({ hasText: 'reviewer-flow' }).filter({ hasText: 'v3.0.0' })
      const progressToggle = article.getByRole('button', { name: /Namespace 可審核人員/ })
      await expect(progressToggle).toHaveAttribute('aria-expanded', 'false')
      await progressToggle.click()
      await expect(article.getByText('Namespace ADMIN：7 人')).toBeVisible()
      await page.screenshot({ path: testInfo.outputPath('progress.png'), fullPage: true })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
      expect(errors).toEqual([])
      expect(failedResponses).toEqual([])
    })
  }
}

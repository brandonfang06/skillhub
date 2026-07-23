import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { loginWithCredentials } from './helpers/session'
import { E2eTestDataBuilder } from './helpers/test-data-builder'

function adminCredentials() {
  return {
    username: process.env.E2E_ADMIN_USERNAME ?? process.env.BOOTSTRAP_ADMIN_USERNAME ?? 'admin',
    password: process.env.E2E_ADMIN_PASSWORD ?? process.env.BOOTSTRAP_ADMIN_PASSWORD ?? 'ChangeMe!2026',
  }
}

test.describe('My Namespaces Data (Real API)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await setEnglishLocale(page)
    await loginWithCredentials(page, adminCredentials(), testInfo)
  })

  test('shows namespace created by request helper', async ({ page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()

    try {
      const namespace = await builder.ensureWritableNamespace()
      await page.goto('/dashboard/namespaces')

      await expect(page.getByRole('heading', { name: 'My Namespaces' })).toBeVisible()
      await expect(page.getByText(`@${namespace.slug}`)).toBeVisible()
    } finally {
      await builder.cleanup()
    }
  })

  test('deletes a writable namespace from the dashboard', async ({ page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()

    try {
      const namespace = await builder.createNamespace('e2e-delete')

      await page.goto('/dashboard/namespaces')

      const namespaceCard = page.getByTestId(`namespace-card-${namespace.slug}`)
      await expect(namespaceCard.getByText(`@${namespace.slug}`)).toBeVisible()

      await page.getByTestId(`delete-namespace-${namespace.slug}`).click()
      await expect(page.getByTestId('namespace-action-dialog-delete')).toBeVisible()

      const deleteResponsePromise = page.waitForResponse((response) =>
        response.request().method() === 'DELETE'
          && response.url().includes(`/api/web/namespaces/${namespace.slug}`),
      )
      await page.getByTestId('namespace-action-confirm-delete').click()
      const deleteResponse = await deleteResponsePromise

      expect(deleteResponse.ok()).toBeTruthy()
      await expect(page.getByText(`@${namespace.slug}`)).toHaveCount(0)
    } finally {
      await builder.cleanup()
    }
  })

  test('disables the delete action when the namespace has dependencies', async ({ page }, testInfo) => {
    const builder = new E2eTestDataBuilder(page, testInfo)
    await builder.init()

    try {
      const namespace = await builder.createNamespace('e2e-delete-guard')

      await builder.publishSkill(namespace.slug, {
        name: `Delete Guard ${Date.now()}`,
        description: 'Prevents namespace deletion during Playwright validation',
      })

      await page.goto('/dashboard/namespaces')

      const namespaceCard = page.getByTestId(`namespace-card-${namespace.slug}`)
      await expect(namespaceCard.getByText(`@${namespace.slug}`)).toBeVisible()
      await expect(namespaceCard.getByTestId(`delete-namespace-${namespace.slug}`)).toBeDisabled()
      await expect(namespaceCard).toContainText('Remove dependencies first: 1 skills, 0 review tasks, 0 promotion requests.')
    } finally {
      await builder.cleanup()
    }
  })
})

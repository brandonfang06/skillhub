import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { loginWithCredentials } from './helpers/session'

const webBasePath = (process.env.E2E_WEB_BASE_PATH ?? '').replace(/\/$/, '')

test.describe('Service Accounts (Real API)', () => {
  test('renders create actions in all supported languages', async ({ page }, testInfo) => {
    await loginWithCredentials(page, {
      username: process.env.E2E_ADMIN_USERNAME ?? 'admin',
      password: process.env.E2E_ADMIN_PASSWORD ?? 'ChangeMe!2026',
    }, testInfo)
    await page.goto(`${webBasePath}/`)

    for (const locale of [
      {
        code: 'en',
        cancel: 'Cancel',
        create: 'Create Service Principal',
        hint: 'The code is immutable after creation.',
      },
      {
        code: 'zh-TW',
        cancel: '取消',
        create: '新增 Service Principal',
        hint: '代碼建立後不可變更',
      },
      {
        code: 'zh',
        cancel: '取消',
        create: '新增 Service Principal',
        hint: '代码创建后不可变更',
      },
    ]) {
      await page.evaluate((language) => window.localStorage.setItem('i18nextLng', language), locale.code)
      await page.goto(`${webBasePath}/admin/service-principals?locale=${locale.code}`)
      await page.getByRole('button', { name: locale.create }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog.getByRole('button', { name: locale.cancel })).toBeVisible()
      await expect(dialog.getByRole('button', { name: locale.create })).toBeVisible()
      await expect(dialog.getByText(new RegExp(locale.hint))).toBeVisible()
      await dialog.getByRole('button', { name: locale.cancel }).click()
    }
  })

  test('creates and revokes an explicitly never-expiring token', async ({ page }, testInfo) => {
    await setEnglishLocale(page)
    await loginWithCredentials(page, {
      username: process.env.E2E_ADMIN_USERNAME ?? 'admin',
      password: process.env.E2E_ADMIN_PASSWORD ?? 'ChangeMe!2026',
    }, testInfo)

    const suffix = Date.now().toString(36)
    const code = `e2e-importer-${suffix}`
    const displayName = `E2E Importer ${suffix}`
    const tokenName = `persistent-gitlab-importer-token-${suffix}-with-a-readable-long-name`

    await page.goto(`${webBasePath}/admin/service-principals`)
    await expect(page.getByRole('heading', { name: 'Service Accounts' })).toBeVisible()
    await page.getByRole('button', { name: 'Create Service Principal' }).click()

    const createDialog = page.getByRole('dialog')
    await expect(createDialog.getByRole('button', { name: 'Cancel' })).toBeVisible()
    await expect(createDialog.getByRole('button', { name: 'Create Service Principal' })).toBeVisible()
    await createDialog.getByLabel('Code').fill(code)
    await createDialog.getByLabel('Display Name').fill(displayName)
    await createDialog.getByRole('button', { name: 'Create Service Principal' }).click()

    const principalRow = page.getByRole('row').filter({ hasText: displayName })
    await expect(principalRow).toBeVisible()
    await principalRow.getByRole('button', { name: 'Manage Tokens' }).click()

    const tokenDialog = page.getByRole('dialog').filter({
      has: page.getByRole('heading', { name: displayName }),
    })
    await tokenDialog.getByLabel('Token Name').fill(tokenName)
    await tokenDialog.getByRole('checkbox', { name: /Never Expires/ }).check()
    await expect(tokenDialog.getByText(/remains valid until it is revoked/)).toBeVisible()
    await expect(tokenDialog.getByLabel('Expiration Date')).toBeDisabled()
    await tokenDialog.getByRole('button', { name: 'Create Token' }).click()

    const secretDialog = page.getByRole('dialog').filter({
      has: page.getByRole('heading', { name: 'Save This Service Token Now' }),
    })
    await expect(secretDialog.getByRole('heading', { name: 'Save This Service Token Now' })).toBeVisible()
    await expect(secretDialog.getByTestId('service-token-secret')).toHaveText(/^st_/)
    await secretDialog.getByRole('button', { name: 'Close' }).last().click()

    const tokenRow = tokenDialog.locator('.rounded-lg.border').filter({ hasText: tokenName })
    await expect(tokenRow).toContainText(tokenName)
    await expect(tokenRow).toContainText('Never Expires')
    await tokenRow.getByRole('button', { name: 'Revoke token' }).click()
    await expect(tokenRow.getByRole('button', { name: 'Revoke token' })).toBeDisabled()

    await tokenDialog.getByRole('button', { name: 'Close' }).first().click()
    await principalRow.getByRole('button', { name: 'Disable' }).click()
    await expect(principalRow.getByText('DISABLED')).toBeVisible()
  })
})

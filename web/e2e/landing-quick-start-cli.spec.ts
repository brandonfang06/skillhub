import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'

test.describe('Landing Quick Start CLI (Real API)', () => {
  test.beforeEach(async ({ page }) => {
    await setEnglishLocale(page)
  })

  test('renders the supported internal CLI onboarding', async ({ page }) => {
    await page.goto('/')

    const cliTab = page.getByRole('button', { name: 'CLI', exact: true })

    await expect(cliTab).toBeVisible()
    await expect(cliTab).toHaveAttribute('aria-pressed', 'true')
    await expect(
      page.getByRole('button', { name: 'I am Agent', exact: true }),
    ).toHaveCount(0)
    await expect(
      page.getByRole('button', { name: 'I am Human', exact: true }),
    ).toHaveCount(0)

    await expect(
      page.getByText('Install the SkillHub CLI locally to run skillhub install for skills.'),
    ).toBeVisible()
    await expect(page.getByText('npm i -g @astron-team/skillhub', { exact: true })).toBeVisible()
  })

  test('keeps the CLI copy action keyboard reachable', async ({ page }) => {
    await page.goto('/')

    const copyButton = page.getByRole('button', { name: 'Copy', exact: true }).first()

    await expect(copyButton).toBeVisible()
    await copyButton.focus()
    await expect(copyButton).toBeFocused()
  })
})

import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { installCollectionMockApi } from './helpers/collection-fixtures'

test('shows a pinned two-registry command and focusable copy action', async ({
  page,
}) => {
  await setEnglishLocale(page)
  await installCollectionMockApi(page, { canCurate: false, role: 'MEMBER' })
  await page.goto('/space/opensource/collections/superpowers')

  await expect(page.locator('code')).toContainText(
    'npx --yes --registry https://nexus.example/npm-group @company/skillhub@0.2.0 collection install @opensource/superpowers',
  )
  await expect(page.locator('code')).toContainText(
    '--registry http://localhost:3000 --version 1.4.0 --scope user',
  )
  const copy = page.getByRole('button', {
    name: 'Copy collection install command',
  })
  await copy.focus()
  await expect(copy).toBeFocused()
})

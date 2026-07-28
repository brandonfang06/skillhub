import { expect, test } from '@playwright/test'

import { setEnglishLocale } from './helpers/auth-fixtures'
import { installCollectionMockApi } from './helpers/collection-fixtures'

test('curator import, collection seed, and changed SHA remain explicit', async ({
  page,
}) => {
  await setEnglishLocale(page)
  const state = await installCollectionMockApi(page, {
    withDraft: true,
    gitlabImportEnabled: true,
  })
  await page.goto(
    '/dashboard/namespaces/opensource/collections/superpowers',
  )

  await page.getByRole('button', { name: 'Import from GitLab' }).click()
  await page
    .getByLabel('GitLab project path')
    .fill('oss-mirrors/superpowers')
  await page.getByRole('button', { name: 'Preview repository' }).click()
  await page.getByRole('checkbox').check()
  await page
    .getByRole('button', { name: 'Import selected skills' })
    .click()
  await page
    .getByRole('button', {
      name: 'Add imported skills to collection draft',
    })
    .click()

  await page.getByRole('button', { name: 'Import from GitLab' }).click()
  await page.getByRole('button', { name: 'Check for updates' }).click()

  await expect(page.getByText('Commit aaaaaaaa → cccccccc')).toBeVisible()
  await expect(page.getByText('skills/brainstorming-v2')).toBeVisible()
  await expect(page.getByRole('checkbox')).not.toBeChecked()

  const update = state.requests.find((request) =>
    request.url().endsWith('/repository-imports/9/check-updates'),
  )
  expect(update?.method()).toBe('POST')
  expect(update?.postData()).toBeNull()
})

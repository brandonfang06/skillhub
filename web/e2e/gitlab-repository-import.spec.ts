import { expect, test } from '@playwright/test'

import { setEnglishLocale } from './helpers/auth-fixtures'
import { installCollectionMockApi } from './helpers/collection-fixtures'

test('curator explicitly previews, imports, and seeds GitLab skills', async ({
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

  await expect(page.getByText('skills/brainstorming')).toBeVisible()
  await page.getByRole('checkbox').check()
  await page
    .getByRole('button', { name: 'Import selected skills' })
    .click()
  await expect(page.getByText('Skill created')).toBeVisible()
  await page
    .getByRole('button', {
      name: 'Add imported skills to collection draft',
    })
    .click()

  const preview = state.requests.find((request) =>
    request.url().endsWith('/repository-imports/preview'),
  )
  const ingest = state.requests.find((request) =>
    request.url().endsWith('/repository-imports/9/ingest'),
  )
  const seed = state.requests.find((request) =>
    request.url().endsWith('/repository-imports/9/collection-draft'),
  )
  expect(preview?.postDataJSON()).toEqual({
    projectPath: 'oss-mirrors/superpowers',
    ref: 'main',
  })
  expect(ingest?.postDataJSON()).toEqual({
    candidates: [
      {
        candidateId: 31,
        targetSlug: 'brainstorming',
        targetVersion: '1.0.0',
        visibility: 'NAMESPACE_ONLY',
      },
    ],
  })
  expect(seed?.postDataJSON()).toEqual({
    collectionSlug: 'superpowers',
    displayName: 'Superpowers',
    summary: 'Curated agent workflows',
    candidateIds: [31],
  })
})

test('does not expose GitLab import to namespace members', async ({ page }) => {
  await setEnglishLocale(page)
  await installCollectionMockApi(page, {
    role: 'MEMBER',
    canCurate: false,
    gitlabImportEnabled: true,
  })
  await page.goto(
    '/dashboard/namespaces/opensource/collections/superpowers',
  )

  await expect(
    page.getByRole('button', { name: 'Import from GitLab' }),
  ).toHaveCount(0)
})

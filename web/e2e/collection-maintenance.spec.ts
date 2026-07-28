import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { installCollectionMockApi } from './helpers/collection-fixtures'

test('requires explicit version confirmation and sends concurrency headers', async ({
  page,
}) => {
  await setEnglishLocale(page)
  const state = await installCollectionMockApi(page, { withDraft: true })
  await page.goto(
    '/dashboard/namespaces/opensource/collections/superpowers',
  )

  await expect(page.getByText(/Suggested next version:/)).toBeVisible()
  await page.getByLabel('Collection version').fill('1.5.0')
  await page.getByRole('button', { name: 'Publish', exact: true }).click()

  await expect
    .poll(() =>
      state.requests.find(
        (request) =>
          request.method() === 'POST' &&
          request.url().endsWith('/collections/opensource/superpowers/publish'),
      ),
    )
    .toBeTruthy()
  const request = state.requests.find((candidate) =>
    candidate.url().endsWith('/collections/opensource/superpowers/publish'),
  )
  expect(request?.headers()['idempotency-key']).toBeTruthy()
  expect(request?.postDataJSON()).toEqual({
    version: '1.5.0',
    draftRevision: 1,
  })
})

import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { installCollectionMockApi } from './helpers/collection-fixtures'

test('keeps MEMBER mutation controls hidden and backend denial authoritative', async ({
  page,
}) => {
  await setEnglishLocale(page)
  await installCollectionMockApi(page, {
    role: 'MEMBER',
    canCurate: false,
  })
  await page.goto('/dashboard/namespaces/opensource/collections')

  await expect(
    page.getByText(/Only namespace OWNER\/ADMIN/),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Create collection' }),
  ).toHaveCount(0)

  const status = await page.evaluate(async () => {
    const response = await fetch('/api/web/namespaces/opensource/collections', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': 'member-denied',
      },
      body: JSON.stringify({
        slug: 'denied',
        displayName: 'Denied',
        summary: 'Denied',
      }),
    })
    return response.status
  })
  expect(status).toBe(403)
})

import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { installCollectionMockApi } from './helpers/collection-fixtures'

test('opens a collection from the separate namespace catalog tab', async ({
  page,
}) => {
  await setEnglishLocale(page)
  await installCollectionMockApi(page)
  await page.goto('/space/opensource')

  await page.getByRole('tab', { name: 'Collections' }).click()
  const card = page.getByRole('link', { name: /Superpowers/ })
  await expect(card).toBeVisible()
  await card.press('Enter')
  await expect(page).toHaveURL(
    /\/space\/opensource\/collections\/superpowers$/,
  )
  await expect(
    page.getByRole('heading', { name: 'Superpowers' }),
  ).toBeVisible()
})

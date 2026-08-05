import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { getSearchCard, prepareSearchSeed, type PreparedSearchSeed } from './helpers/search-seed'

const SEARCH_URL = (q: string) => `./search?q=${encodeURIComponent(q)}&sort=relevance&page=0&starredOnly=false`

function latestSeed(seed: PreparedSearchSeed) {
  return {
    skill: seed.skills[seed.skills.length - 1],
    skillName: seed.skillNames[seed.skillNames.length - 1],
  }
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

let seeded: PreparedSearchSeed | undefined

test.describe('Public Skill Detail Anonymous Access (Real API)', () => {
  test.beforeAll(async ({ browser }, testInfo) => {
    seeded = await prepareSearchSeed(browser, testInfo, { count: 1 })
  })

  test.afterAll(async () => {
    await seeded?.dispose()
    seeded = undefined
  })

  test.beforeEach(async ({ page }) => {
    await setEnglishLocale(page)
  })

  test('gates protected content until login and returns to the public skill detail', async ({ page }) => {
    const current = latestSeed(seeded!)
    const protectedContentResponses: number[] = []
    const protectedMutationRequests: string[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (
        request.method() !== 'GET'
        && /\/api\/web\/skills\/[^/]+(?:\/(?:star|subscription|rating|reports))$/.test(url.pathname)
      ) {
        protectedMutationRequests.push(url.pathname)
      }
    })
    page.on('response', (response) => {
      const url = new URL(response.url())
      if (/\/versions\/[^/]+\/file$/.test(url.pathname)) {
        protectedContentResponses.push(response.status())
      }
    })

    await page.goto(SEARCH_URL(seeded!.keyword))
    const card = getSearchCard(page, current.skillName)
    await expect(card).toBeVisible({ timeout: 15_000 })

    await card.click()

    await expect(page).toHaveURL(new RegExp(`/space/${current.skill.namespace}/${current.skill.slug}(\\?|$)`))
    await expect(page).not.toHaveURL(/\/login\?returnTo=/)
    await expect(page.getByRole('heading', { name: current.skillName, exact: true }).first()).toBeVisible()
    await expect(page.getByText('Sign in to view the README')).toBeVisible()
    await expect(page.getByText('Install', { exact: true })).toBeVisible()
    const skillhubNamespace = current.skill.namespace === 'global'
      ? ''
      : ` --namespace ${current.skill.namespace}`

    await expect(page.getByRole('tab', { name: 'SkillHub CLI' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByText(new RegExp(`npx @astron-team/skillhub@latest install ${escapeRegExp(current.skill.slug)}${escapeRegExp(skillhubNamespace)} --registry`))).toBeVisible()
    await expect(page.getByRole('button', { name: 'Copy' }).first()).toBeVisible()

    await page.getByRole('tab', { name: 'Files' }).click()
    await expect(page.getByText('Sign in to preview file contents.').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'SKILL.md' }).first()).toBeVisible()
    await expect(page.getByText('Operation failed')).toHaveCount(0)
    expect(protectedContentResponses).toEqual([])

    const detailUrl = new URL(page.url())
    const skillPathStart = detailUrl.pathname.indexOf('/space/')
    const expectedReturnTo = `${detailUrl.pathname.slice(skillPathStart)}${detailUrl.search}`

    await page.getByRole('button', { name: 'SKILL.md' }).first().click()
    await expect(page).toHaveURL(/\/login\?returnTo=/)
    expect(new URL(page.url()).searchParams.get('returnTo')).toBe(expectedReturnTo)
    expect(protectedContentResponses).toEqual([])

    await page.goBack()
    await expect(page.getByRole('heading', { name: current.skillName, exact: true }).first()).toBeVisible()

    await page.getByRole('button', { name: /^Star \(\d+\)$/ }).click()
    await expect(page).toHaveURL(/\/login\?returnTo=/)
    expect(new URL(page.url()).searchParams.get('returnTo')).toBe(expectedReturnTo)
    expect(protectedMutationRequests).toEqual([])

    await page.goBack()
    await expect(page.getByRole('heading', { name: current.skillName, exact: true }).first()).toBeVisible()
    await page.getByRole('tab', { name: 'Overview' }).click()
    await page.getByRole('button', { name: 'Sign in to view' }).click()
    await expect(page).toHaveURL(/\/login\?returnTo=/)
    expect(new URL(page.url()).searchParams.get('returnTo')).toBe(expectedReturnTo)

    await page.getByLabel('Username').fill(
      process.env.E2E_ADMIN_USERNAME ?? process.env.BOOTSTRAP_ADMIN_USERNAME ?? 'admin',
    )
    await page.getByRole('textbox', { name: 'Password', exact: true }).fill(
      process.env.E2E_ADMIN_PASSWORD ?? process.env.BOOTSTRAP_ADMIN_PASSWORD ?? 'ChangeMe!2026',
    )
    await page.getByRole('button', { name: 'Login', exact: true }).click()

    await expect(page.getByRole('heading', { name: current.skillName, exact: true }).first()).toBeVisible()
    await expect(page.getByText('Source: README.md')).toBeVisible()
    await expect(page.getByText('Sign in to view the README')).toHaveCount(0)
    expect(protectedContentResponses.length).toBeGreaterThan(0)
    expect(protectedContentResponses.every((status) => status === 200)).toBe(true)

    await page.getByRole('tab', { name: 'Files' }).click()
    await page.getByRole('button', { name: 'SKILL.md' }).first().click()
    await expect(page.getByRole('dialog')).toContainText('Generated by Playwright E2E.')

    await page.reload()
    await expect(page).toHaveURL(new RegExp(`/space/${current.skill.namespace}/${current.skill.slug}(\\?|$)`))
    await expect(page.getByRole('heading', { name: current.skillName, exact: true }).first()).toBeVisible()
  })
})

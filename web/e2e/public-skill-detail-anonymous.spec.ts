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

  test('allows anonymous users to open a public skill detail and view install content', async ({ page }) => {
    const current = latestSeed(seeded!)
    const protectedContentResponses: number[] = []
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
    await expect(page.getByRole('heading', { name: current.skillName, exact: true })).toBeVisible()
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

    await page.getByRole('tab', { name: 'Overview' }).click()
    const detailUrl = new URL(page.url())
    const skillPathStart = detailUrl.pathname.indexOf('/space/')
    const expectedReturnTo = `${detailUrl.pathname.slice(skillPathStart)}${detailUrl.search}`
    await page.getByRole('button', { name: 'Sign in to view' }).click()
    await expect(page).toHaveURL(/\/login\?returnTo=/)
    expect(new URL(page.url()).searchParams.get('returnTo')).toBe(expectedReturnTo)
  })
})

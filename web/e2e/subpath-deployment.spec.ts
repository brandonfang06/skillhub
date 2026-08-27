import { expect, test, type Page, type Route } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'

const basePath = '/skillhub'
const reviewId = 13

function envelope(data: unknown) {
  return {
    code: 0,
    msg: 'success',
    data,
    timestamp: '2026-08-04T00:00:00Z',
    requestId: 'subpath-e2e',
  }
}

const principal = {
  userId: 'subpath-reviewer',
  displayName: 'Subpath Reviewer',
  email: 'reviewer@example.test',
  avatarUrl: '',
  oauthProvider: 'keycloak',
  canChangePassword: false,
  platformRoles: ['SKILL_ADMIN', 'SUPER_ADMIN'],
}

type ObservedRequests = {
  apiRootEscapes: string[]
  oauthPaths: string[]
  oauthCallbackPaths: string[]
  cliRedirects: string[]
  csvPaths: string[]
  downloadEventPaths: string[]
  ssePaths: string[]
  tokenPaths: string[]
  protectedContentPaths: string[]
}

function createObservedRequests(): ObservedRequests {
  return {
    apiRootEscapes: [],
    oauthPaths: [],
    oauthCallbackPaths: [],
    cliRedirects: [],
    csvPaths: [],
    downloadEventPaths: [],
    ssePaths: [],
    tokenPaths: [],
    protectedContentPaths: [],
  }
}

const review = {
  id: reviewId,
  namespace: 'global',
  skillSlug: 'subpath-skill',
  version: '1.2.0',
  status: 'PENDING',
  submittedBy: 'owner-1',
  submittedByName: 'Owner One',
  submittedAt: '2026-08-04T00:00:00Z',
  reviewedBy: null,
  reviewedByName: null,
  reviewedAt: null,
  reviewComment: null,
}

const reviewSkillDetail = {
  skill: {
    id: 17,
    slug: 'subpath-skill',
    displayName: 'Subpath Skill',
    summary: 'Production build loaded through a stripped public prefix',
    visibility: 'PUBLIC',
    status: 'ACTIVE',
    downloadCount: 4,
    starCount: 1,
    ratingCount: 0,
    hidden: false,
    namespace: 'global',
    canManageLifecycle: false,
    canSubmitPromotion: false,
    canInteract: false,
    canReport: false,
    resolutionMode: 'REVIEW_TASK',
  },
  versions: [
    {
      id: 52,
      version: '1.2.0',
      status: 'PENDING_REVIEW',
      changelog: 'Subpath release',
      fileCount: 1,
      totalSize: 96,
      publishedAt: '2026-08-04T00:00:00Z',
      downloadAvailable: true,
    },
  ],
  files: [],
  documentationPath: 'SKILL.md',
  documentationContent: '# Subpath Skill',
  downloadUrl: `${basePath}/api/web/reviews/${reviewId}/download`,
  activeVersion: '1.2.0',
  sourceProvenance: {
    repositoryUrl: 'https://github.com/example/subpath-skill',
    repositoryRevisionSha: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    sourceRefType: 'TAG',
    sourceRef: 'v1.2.0',
    sourcePath: 'skills/subpath-skill',
    contentFingerprint: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    browseUrl: 'https://github.com/example/subpath-skill/tree/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/skills/subpath-skill',
  },
}

const publicSkill = {
  id: 17,
  slug: 'subpath-skill',
  displayName: 'Subpath Skill',
  ownerId: 'owner-1',
  ownerDisplayName: 'Owner One',
  summary: 'Production build loaded through a stripped public prefix',
  visibility: 'PUBLIC',
  status: 'ACTIVE',
  downloadCount: 4,
  starCount: 1,
  subscriptionCount: 0,
  ratingAvg: 5,
  ratingCount: 1,
  hidden: false,
  namespace: 'global',
  labels: [],
  canManageLifecycle: false,
  canSubmitPromotion: false,
  canInteract: true,
  canReport: true,
  headlineVersion: { id: 52, version: '1.2.0', status: 'PUBLISHED' },
  publishedVersion: { id: 52, version: '1.2.0', status: 'PUBLISHED' },
  ownerPreviewVersion: null,
  ownerPreviewReviewComment: null,
  resolutionMode: 'PUBLISHED',
}

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  })
}

async function installMockApi(
  page: Page,
  options: { authenticated: boolean },
  observed: ObservedRequests,
) {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (url.origin === 'http://127.0.0.1:48765' && url.pathname === '/callback') {
      observed.cliRedirects.push(`${url.pathname}${url.hash}`)
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<h1>CLI loopback reached</h1>',
      })
      return
    }

    if (url.origin !== 'http://127.0.0.1:3190' && url.origin !== 'http://localhost:3000') {
      await route.continue()
      return
    }

    if (url.pathname.startsWith('/api/')) {
      observed.apiRootEscapes.push(url.pathname)
    }

    if (url.pathname.startsWith(`${basePath}/oauth2/authorization/keycloak`)) {
      observed.oauthPaths.push(`${url.pathname}${url.search}`)
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<h1>OAuth boundary reached</h1>',
      })
      return
    }

    if (url.pathname === `${basePath}/login/oauth2/code/keycloak`) {
      observed.oauthCallbackPaths.push(`${url.pathname}${url.search}`)
      await route.fulfill({
        status: 307,
        headers: { Location: `${basePath}/dashboard` },
        body: '',
      })
      return
    }

    if (!url.pathname.startsWith(`${basePath}/api/`) && !url.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    const path = url.pathname.startsWith(basePath)
      ? url.pathname.slice(basePath.length)
      : url.pathname

    if (/\/api\/web\/skills\/[^/]+\/[^/]+\/versions\/[^/]+\/file$/.test(path)) {
      observed.protectedContentPaths.push(url.pathname)
    }

    if (path === '/api/v1/auth/me') {
      if (options.authenticated) {
        await fulfillJson(route, envelope(principal))
      } else {
        await fulfillJson(route, { detail: 'error.auth.required' }, 401)
      }
      return
    }

    if (path === '/api/v1/auth/providers') {
      await fulfillJson(route, envelope([]))
      return
    }

    if (path === '/api/v1/auth/methods') {
      await fulfillJson(route, envelope([
        {
          id: 'oauth-keycloak',
          methodType: 'OAUTH_REDIRECT',
          provider: 'keycloak',
          displayName: 'Keycloak',
          actionUrl: `${basePath}/oauth2/authorization/keycloak?returnTo=%2Fdashboard`,
        },
      ]))
      return
    }

    if (path === '/api/v1/auth/logout') {
      await route.fulfill({ status: 204, body: '' })
      return
    }

    if (path === `/api/web/reviews/${reviewId}`) {
      await fulfillJson(route, envelope(review))
      return
    }

    if (path === `/api/web/reviews/${reviewId}/skill-detail`) {
      await fulfillJson(route, envelope(reviewSkillDetail))
      return
    }

    if (path === '/api/web/me/namespaces') {
      await fulfillJson(route, envelope([]))
      return
    }

    if (path === '/api/web/notifications/unread-count') {
      await fulfillJson(route, envelope({ count: 0 }))
      return
    }

    if (path === '/api/web/notifications/sse') {
      observed.ssePaths.push(url.pathname)
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': ready\n\n' })
      return
    }

    if (path === '/api/web/skills') {
      await fulfillJson(route, envelope({
        items: [publicSkill],
        total: 1,
        page: 0,
        size: 12,
      }))
      return
    }

    if (path === '/api/web/labels') {
      await fulfillJson(route, envelope([]))
      return
    }

    if (path === '/api/v1/tokens' && route.request().method() === 'POST') {
      observed.tokenPaths.push(url.pathname)
      await fulfillJson(route, envelope({
        id: 91,
        name: 'Subpath CLI',
        token: 'skillhub_subpath_token',
        tokenPrefix: 'skillhub_sub',
        createdAt: '2026-08-04T00:00:00Z',
      }))
      return
    }

    if (path === '/api/v1/admin/labels') {
      await fulfillJson(route, envelope([]))
      return
    }

    if (path === '/api/v1/admin/namespace-analytics') {
      await fulfillJson(route, envelope({
        summary: {
          namespaceCount: 1,
          maintainerCount: 2,
          skillCount: 3,
          lifetimeDownloads: 80,
          periodDownloads: 12,
        },
        period: {
          startTime: '2026-07-05T00:00:00Z',
          endTime: '2026-08-04T00:00:00Z',
          source: 'cli',
          retentionMonths: 12,
        },
        items: [{
          namespaceId: 17,
          slug: 'platform',
          displayName: 'Platform',
          type: 'TEAM',
          status: 'ACTIVE',
          maintainerCount: 2,
          skillCount: 3,
          lifetimeDownloads: 80,
          periodDownloads: 12,
        }],
        page: 0,
        size: 20,
        total: 1,
      }))
      return
    }

    if (path === '/api/v1/admin/namespace-analytics.csv') {
      observed.csvPaths.push(url.pathname)
      await route.fulfill({
        status: 200,
        contentType: 'text/csv; charset=utf-8',
        headers: {
          'Content-Disposition': 'attachment; filename="skillhub-namespace-analytics.csv"',
          'X-SkillHub-Export-Truncated': 'false',
          'X-SkillHub-Export-Row-Limit': '10000',
        },
        body: '\ufeffnamespace_id,namespace_slug,display_name\r\n17,platform,Platform\r\n',
      })
      return
    }

    if (path === '/api/v1/admin/download-events') {
      observed.downloadEventPaths.push(`${url.pathname}${url.search}`)
      await fulfillJson(route, envelope({
        items: [{
          id: 81,
          skillId: 17,
          skillVersionId: 52,
          namespace: 'global',
          slug: 'subpath-skill',
          version: '1.2.0',
          source: 'web',
          userId: 'oauth-user-81',
          username: 'Alex Chen',
          requestId: 'subpath-download-event',
          ipAddress: '127.0.0.1',
          userAgent: 'subpath-e2e',
          createdAt: '2026-08-04T00:00:00Z',
        }],
        total: 1,
        page: 0,
        size: 20,
      }))
      return
    }

    if (path === '/api/v1/admin/download-events.csv') {
      observed.csvPaths.push(url.pathname)
      await route.fulfill({
        status: 200,
        contentType: 'text/csv',
        headers: { 'Content-Disposition': 'attachment; filename="download-events.csv"' },
        body: 'createdAt,userId,namespace,slug,version,source\n',
      })
      return
    }

    if (path === '/api/v1/skills/17/versions/52/security-audit') {
      await fulfillJson(route, envelope([]))
      return
    }

    if (path === '/api/web/skills/global/subpath-skill') {
      await fulfillJson(route, envelope(publicSkill))
      return
    }

    if (path === '/api/web/skills/global/subpath-skill/versions') {
      await fulfillJson(route, envelope({
        items: [{
          id: 52,
          version: '1.2.0',
          status: 'PUBLISHED',
          changelog: 'Subpath release',
          fileCount: 1,
          totalSize: 96,
          publishedAt: '2026-08-04T00:00:00Z',
          downloadAvailable: true,
          complianceSnapshot: {
            schemaVersion: '1.0',
            digest: `sha256:${'d'.repeat(64)}`,
            items: [{
              standard: 'soc2',
              version: '2026',
              controlId: 'CC7.2',
              title: 'Publisher-declared monitoring activity',
              evidence: [{
                type: 'external-url',
                url: 'https://example.test/evidence/with/a/very/long/path/that/must/wrap',
                sha256: 'a'.repeat(64),
              }],
            }],
          },
        }],
        total: 1,
        page: 0,
        size: 20,
      }))
      return
    }

    if (path === '/api/web/skills/global/subpath-skill/versions/1.2.0/files') {
      await fulfillJson(route, envelope([{ id: 201, filePath: 'SKILL.md', fileSize: 96, contentType: 'text/markdown', sha256: 'hash' }]))
      return
    }

    if (path === '/api/web/skills/global/subpath-skill/versions/1.2.0') {
      await fulfillJson(route, envelope({
        id: 52,
        version: '1.2.0',
        status: 'PUBLISHED',
        fileCount: 1,
        totalSize: 96,
        publishedAt: '2026-08-04T00:00:00Z',
        sourceProvenance: reviewSkillDetail.sourceProvenance,
      }))
      return
    }

    if (path === '/api/web/skills/global/subpath-skill/versions/1.2.0/file') {
      await route.fulfill({ status: 200, contentType: 'text/markdown', body: '# Subpath Skill\n' })
      return
    }

    if (path === '/api/web/skills/global/subpath-skill/versions/1.2.0/download') {
      await route.fulfill({
        status: 200,
        contentType: 'application/zip',
        headers: { 'Content-Disposition': 'attachment; filename="subpath-skill.zip"' },
        body: 'zip-bytes',
      })
      return
    }

    if (path === '/api/web/skills/17/star' || path === '/api/web/skills/17/subscription') {
      await fulfillJson(route, envelope(false))
      return
    }

    if (path === '/api/web/skills/17/rating') {
      await fulfillJson(route, envelope({ score: null }))
      return
    }

    if (path === '/api/web/skills/global/subpath-skill/labels') {
      await fulfillJson(route, envelope([]))
      return
    }

    await fulfillJson(route, envelope({ items: [], total: 0, page: 0, size: 20 }))
  })
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}

test.describe('SkillHub production subpath deployment', () => {
  test.beforeEach(async ({ page }) => {
    await setEnglishLocale(page)
  })

  test('loads a lazy review route under the prefix across reload and viewports', async ({ page }) => {
    const observed = createObservedRequests()
    const browserErrors: string[] = []
    page.on('pageerror', (error) => browserErrors.push(error.message))
    await installMockApi(page, { authenticated: true }, observed)

    await page.goto(`${basePath}/dashboard/reviews/${reviewId}`)
    await expect(page.getByRole('heading', { name: 'Review Detail' })).toBeVisible()
    await expect.poll(() => page.evaluate(() => performance.getEntriesByType('resource').map((entry) => entry.name)))
      .toContainEqual(expect.stringMatching(/\/skillhub\/assets\/review-detail-[^/]+\.js/))

    await page.reload()
    await expect(page.getByRole('heading', { name: 'Review Detail' })).toBeVisible()

    await expectNoHorizontalOverflow(page)

    expect(observed.apiRootEscapes).toEqual([])
    expect(browserErrors).toEqual([])
  })

  test('keeps authenticated download and logout traffic under the prefix', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: true }, observed)

    await page.goto(`${basePath}/space/global/subpath-skill`)
    await expect(page.getByRole('heading', { name: 'Subpath Skill', exact: true }).first()).toBeVisible()
    await expect(page.getByRole('link', { name: 'View immutable source on GitHub' })).toHaveAttribute(
      'href',
      reviewSkillDetail.sourceProvenance.browseUrl,
    )
    await expectNoHorizontalOverflow(page)

    const downloadRequest = page.waitForRequest((request) =>
      new URL(request.url()).pathname === `${basePath}/api/web/skills/global/subpath-skill/versions/1.2.0/download`,
    )
    await page.getByRole('button', { name: 'Download' }).click()
    await downloadRequest

    const logoutRequest = page.waitForRequest((request) =>
      new URL(request.url()).pathname === `${basePath}/api/v1/auth/logout`,
    )
    await page.getByRole('button', { name: 'Subpath Reviewer' }).click()
    await page.getByRole('button', { name: 'Logout' }).click()
    await logoutRequest
    await expect(page).toHaveURL('http://127.0.0.1:3190/skillhub/')
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('renders publisher compliance declarations without mobile overflow', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: true }, observed)

    await page.goto(`${basePath}/space/global/subpath-skill`)
    await page.getByRole('tab', { name: 'Versions' }).click()
    await expect(page.getByRole('region', { name: 'Publisher compliance declarations' })).toBeVisible()
    await page.getByRole('button', { name: 'Expand details' }).click()
    await expect(page.getByText('https://example.test/evidence/with/a/very/long/path/that/must/wrap')).toBeVisible()
    await expectNoHorizontalOverflow(page)

    expect(observed.apiRootEscapes).toEqual([])
  })

  test('selects and configures multiple Skills under the prefix across reload and viewports', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: true }, observed)

    await page.goto(`${basePath}/search`)
    const multiInstallButton = page.getByRole('button', { name: 'Install multiple Skills' })
    await expect(page.getByText('Select up to 20 and copy install commands')).toBeVisible()
    const multiInstallBox = await multiInstallButton.boundingBox()
    expect(multiInstallBox!.width).toBeGreaterThanOrEqual(280)
    expect(multiInstallBox!.height).toBeGreaterThanOrEqual(60)
    await multiInstallButton.click()
    const skillCheckbox = page.getByRole('checkbox', { name: 'Select Subpath Skill' })
    const skillHeading = page.getByRole('heading', { name: 'Subpath Skill', exact: true })
    await skillCheckbox.check()
    await expect(page.getByRole('status')).toHaveText('1 / 20 Skills selected')
    const checkboxBox = await skillCheckbox.boundingBox()
    const headingBox = await skillHeading.boundingBox()
    expect(checkboxBox!.x).toBeLessThan(headingBox!.x)
    expect(checkboxBox!.y).toBeLessThan(headingBox!.y + headingBox!.height)

    const continueButton = page.getByRole('button', { name: 'Continue to install' })
    await expect(continueButton).toBeInViewport()
    const continueBox = await continueButton.boundingBox()
    expect(continueBox!.y).toBeLessThan(checkboxBox!.y)

    await page.getByRole('button', { name: 'Clear selection' }).click()
    await expect(multiInstallButton).toBeFocused()

    await multiInstallButton.click()
    await page.getByRole('checkbox', { name: 'Select Subpath Skill' }).check()
    await page.reload()
    await expect(page.getByRole('status')).toHaveText('1 / 20 Skills selected')

    await continueButton.click()
    await expect(page).toHaveURL(`http://127.0.0.1:3190${basePath}/install`)
    await expect(page.getByRole('heading', { name: 'Install Skills' })).toBeFocused()
    await page.getByLabel('Agent targets').selectOption('codex')
    await expect(page.getByText(
      'npx @astron-team/skillhub@latest install subpath-skill --registry http://127.0.0.1:3190/skillhub --scope user --agent codex --force',
      { exact: true },
    )).toBeVisible()
    const directMode = page.getByRole('radio', { name: 'Direct Agent' })
    const interactiveMode = page.getByRole('radio', { name: 'Terminal interactive' })
    await expect(directMode).toBeChecked()
    await interactiveMode.check()
    await expect(page.getByLabel('Agent targets')).toHaveCount(0)
    await expect(page.getByText(
      'Each Skill asks once in an interactive Terminal; choose multiple Agents or Generic there. Latest versions replace all selected target directories. Not for CI or background jobs.',
      { exact: true },
    )).toBeVisible()
    await expect(page.getByText(
      'npx @astron-team/skillhub@latest install subpath-skill --registry http://127.0.0.1:3190/skillhub --scope user --force',
      { exact: true },
    )).toBeVisible()
    await expect(page.getByRole('button', { name: 'Copy all commands' })).toBeEnabled()
    const targetsHeading = page.getByRole('heading', { name: 'Install target' })
    const commandsHeading = page.getByRole('heading', { name: 'Terminal commands' })
    const selectedSummary = page.getByText('1 Skills selected', { exact: true })
    const selectedDisclosure = page.locator('details').filter({ hasText: '1 Skills selected' })
    await expect(selectedDisclosure).toHaveAttribute('open', '')
    const targetBox = await targetsHeading.boundingBox()
    const commandsBox = await commandsHeading.boundingBox()
    const selectedBox = await selectedSummary.boundingBox()
    expect(targetBox!.y).toBeLessThan(commandsBox!.y)
    expect(commandsBox!.y).toBeLessThan(selectedBox!.y)
    expect(selectedBox!.y + selectedBox!.height).toBeLessThanOrEqual(await page.evaluate(() => window.innerHeight))
    await directMode.check()
    await expect(page.getByLabel('Agent targets')).toHaveValue('codex')
    await expect(page.getByText('Verify the Terminal identity')).toHaveCount(0)
    await expect(page.getByRole('checkbox', { name: 'Update/reinstall existing Skills to the latest version' })).toHaveCount(0)
    await expectNoHorizontalOverflow(page)

    await page.getByRole('button', { name: 'Clear selection' }).click()
    await expect(page.getByRole('heading', { name: 'Install Skills' })).toBeFocused()
    await expect(page.getByText('No Skills are selected in this browser tab.')).toBeVisible()
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('keeps the Traditional Chinese multi-install entry readable without crowding', async ({ page }) => {
    const observed = createObservedRequests()
    await page.addInitScript(() => window.localStorage.setItem('i18nextLng', 'zh-TW'))
    await installMockApi(page, { authenticated: true }, observed)

    await page.goto(`${basePath}/search`)
    const multiInstallButton = page.getByRole('button', { name: '批次安裝多個 Skills' })
    await expect(page.getByText('一次選取最多 20 個，並複製安裝指令')).toBeVisible()
    const multiInstallBox = await multiInstallButton.boundingBox()
    expect(multiInstallBox!.width).toBeGreaterThanOrEqual(280)
    expect(multiInstallBox!.height).toBeGreaterThanOrEqual(60)
    await expectNoHorizontalOverflow(page)
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('sends anonymous multi-Skill selection through login with a logical return path', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: false }, observed)

    await page.goto(`${basePath}/search`)
    await page.getByRole('button', { name: 'Install multiple Skills' }).click()

    await expect(page).toHaveURL(/\/skillhub\/login\?returnTo=/)
    const loginUrl = new URL(page.url())
    expect(loginUrl.pathname).toBe('/skillhub/login')
    expect(loginUrl.searchParams.get('returnTo')).toBe(
      '/search?q=&sort=newest&page=0&starredOnly=false',
    )
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('redirects anonymous users and reaches OAuth without duplicating the prefix', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: false }, observed)

    await page.goto(`${basePath}/dashboard`)
    await expect(page).toHaveURL(/\/skillhub\/login\?returnTo=%2Fdashboard$/)
    await page.getByRole('tab', { name: 'OAuth' }).click()
    await page.getByRole('button', { name: 'Login with Keycloak' }).click()
    await expect(page.getByRole('heading', { name: 'OAuth boundary reached' })).toBeVisible()

    expect(observed.oauthPaths).toEqual([
      '/skillhub/oauth2/authorization/keycloak?returnTo=%2Fdashboard',
    ])
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('keeps anonymous public skill content gated under the prefix', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: false }, observed)

    await page.goto(`${basePath}/space/global/subpath-skill`)
    await expect(page.getByRole('heading', { name: 'Subpath Skill', exact: true }).first()).toBeVisible()
    await expect(page.getByText('Sign in to view the README')).toBeVisible()
    await page.getByRole('tab', { name: 'Files' }).click()
    await expect(page.getByText('Sign in to preview file contents.').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'SKILL.md' }).first()).toBeVisible()
    expect(observed.protectedContentPaths).toEqual([])

    await page.getByRole('tab', { name: 'Overview' }).click()
    await page.getByRole('button', { name: 'Sign in to view' }).click()
    await expect(page).toHaveURL(
      /\/skillhub\/login\?returnTo=%2Fspace%2Fglobal%2Fsubpath-skill$/,
    )
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('loads landing and authenticated dashboard while SSE stays under the prefix', async ({ page }) => {
    const anonymousObserved = createObservedRequests()
    await installMockApi(page, { authenticated: false }, anonymousObserved)

    await page.goto(`${basePath}/`)
    await expect(page.getByRole('heading', { name: 'SkillHub', exact: true })).toBeVisible()
    await expectNoHorizontalOverflow(page)
    expect(anonymousObserved.apiRootEscapes).toEqual([])

    await page.unroute('**/*')
    const authenticatedObserved = createObservedRequests()
    await installMockApi(page, { authenticated: true }, authenticatedObserved)
    const sseRequest = page.waitForRequest((request) =>
      new URL(request.url()).pathname === `${basePath}/api/web/notifications/sse`,
    )
    await page.goto(`${basePath}/dashboard`)
    await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible()
    await sseRequest
    await expectNoHorizontalOverflow(page)

    expect(authenticatedObserved.ssePaths).toContain(`${basePath}/api/web/notifications/sse`)
    expect(authenticatedObserved.apiRootEscapes).toEqual([])
  })

  test('follows the OAuth callback to its prefixed dashboard target', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: true }, observed)

    await page.goto(`${basePath}/login/oauth2/code/keycloak?code=e2e-code&state=e2e-state`)
    await expect(page).toHaveURL(`http://127.0.0.1:3190${basePath}/dashboard`)
    await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible()
    await expectNoHorizontalOverflow(page)

    expect(observed.oauthCallbackPaths).toEqual([
      `${basePath}/login/oauth2/code/keycloak?code=e2e-code&state=e2e-state`,
    ])
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('creates a CLI token under the prefix and returns the canonical registry', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: true }, observed)
    const redirectUri = encodeURIComponent('http://127.0.0.1:48765/callback')

    await page.goto(`${basePath}/cli/auth?redirect_uri=${redirectUri}&state=e2e-state&label=Subpath%20CLI`)
    await expect(page.getByRole('heading', { name: 'CLI loopback reached' })).toBeVisible()

    expect(observed.tokenPaths).toEqual([`${basePath}/api/v1/tokens`])
    expect(observed.cliRedirects).toHaveLength(1)
    const hash = new URLSearchParams(new URL(page.url()).hash.slice(1))
    expect(hash.get('token')).toBe('skillhub_subpath_token')
    expect(hash.get('registry')).toBe('http://127.0.0.1:3190/skillhub')
    expect(hash.get('state')).toBe('e2e-state')
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('exports admin download events CSV under the prefix', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: true }, observed)

    await page.goto(`${basePath}/admin/download-events`)
    await expect(page.getByRole('heading', { name: 'Download Events', exact: true })).toBeVisible()
    const exportLink = page.getByRole('link', { name: 'Export CSV' })
    await expect(exportLink).toHaveAttribute('href', `${basePath}/api/v1/admin/download-events.csv`)
    const downloadEvent = page.waitForEvent('download')
    await exportLink.click()
    const download = await downloadEvent
    await expectNoHorizontalOverflow(page)

    expect(new URL(download.url()).pathname).toBe(`${basePath}/api/v1/admin/download-events.csv`)
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('filters download events by readable user identity under the prefix', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: true }, observed)

    await page.goto(`${basePath}/admin/download-events`)
    const filter = page.getByPlaceholder('User name or ID...')
    const filteredRequest = page.waitForRequest((request) => {
      const url = new URL(request.url())
      return url.pathname === `${basePath}/api/v1/admin/download-events`
        && url.searchParams.get('userQuery') === 'Alex Chen'
    })
    await filter.fill('Alex Chen')
    await filteredRequest

    const userCell = page.locator('tbody tr td').nth(1)
    await expect(userCell.locator('.font-medium')).toHaveText('Alex Chen')
    await expect(userCell.locator('.font-mono')).toHaveText('oauth-user-81')
    await expect(page.getByRole('link', { name: 'Export CSV' })).toHaveAttribute(
      'href',
      `${basePath}/api/v1/admin/download-events.csv?userQuery=Alex+Chen`,
    )
    await expectNoHorizontalOverflow(page)

    expect(observed.downloadEventPaths).toContain(
      `${basePath}/api/v1/admin/download-events?userQuery=Alex+Chen&page=0&size=20`,
    )
    expect(observed.apiRootEscapes).toEqual([])
  })

  test('loads namespace analytics and drills into events under the prefix', async ({ page }) => {
    const observed = createObservedRequests()
    await installMockApi(page, { authenticated: true }, observed)
    const analyticsRequest = page.waitForRequest((request) =>
      new URL(request.url()).pathname === `${basePath}/api/v1/admin/namespace-analytics`,
    )

    await page.goto(`${basePath}/admin/namespace-analytics`)
    await expect(page.getByRole('heading', { name: 'Namespace Analytics', exact: true })).toBeVisible()
    await analyticsRequest
    await expect(page.getByText('@platform')).toBeVisible()

    const reloadRequest = page.waitForRequest((request) =>
      new URL(request.url()).pathname === `${basePath}/api/v1/admin/namespace-analytics`,
    )
    await page.reload()
    await reloadRequest
    await expect(page.getByRole('heading', { name: 'Namespace Analytics', exact: true })).toBeVisible()

    const filteredRequest = page.waitForRequest((request) => {
      const url = new URL(request.url())
      return url.pathname === `${basePath}/api/v1/admin/namespace-analytics`
        && url.searchParams.get('namespaceType') === 'GLOBAL'
    })
    await page.getByRole('combobox').first().click()
    await page.getByRole('option', { name: 'Global', exact: true }).click()
    await filteredRequest
    await expect(page).toHaveURL(/\/skillhub\/admin\/namespace-analytics\?.*namespaceType=GLOBAL/)

    const exportRequest = page.waitForRequest((request) =>
      new URL(request.url()).pathname === `${basePath}/api/v1/admin/namespace-analytics.csv`,
    )
    const downloadEvent = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export CSV' }).click()
    const request = await exportRequest
    const download = await downloadEvent
    const exportUrl = new URL(request.url())
    expect(exportUrl.searchParams.get('namespaceType')).toBe('GLOBAL')
    expect(exportUrl.searchParams.get('source')).toBeNull()
    expect(exportUrl.searchParams.has('page')).toBe(false)
    expect(exportUrl.searchParams.has('size')).toBe(false)
    expect(download.suggestedFilename()).toBe('skillhub-namespace-analytics.csv')
    expect(observed.csvPaths).toEqual([`${basePath}/api/v1/admin/namespace-analytics.csv`])
    await expectNoHorizontalOverflow(page)

    await page.getByRole('button', { name: 'View Events' }).click()
    await expect(page).toHaveURL(/\/skillhub\/admin\/download-events\?/)
    const drillDownUrl = new URL(page.url())
    expect(drillDownUrl.searchParams.get('namespace')).toBe('platform')
    expect(drillDownUrl.searchParams.get('startTime')).toBe('2026-07-05T00:00:00Z')
    expect(drillDownUrl.searchParams.get('endTime')).toBe('2026-08-04T00:00:00Z')
    expect(drillDownUrl.searchParams.get('source')).toBe('cli')
    await expectNoHorizontalOverflow(page)

    expect(observed.apiRootEscapes).toEqual([])
  })
})

import { expect, test, type Page, type Route } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'

const skill = {
  id: 17,
  namespace: 'global',
  slug: 'browser-flow',
  displayName: 'Browser Flow Skill',
  summary: 'A public skill used by the browser mock API smoke flow',
  version: '1.0.0',
}

function envelope(data: unknown) {
  return {
    code: 0,
    msg: 'success',
    data,
    timestamp: '2026-06-20T00:00:00Z',
    requestId: 'browser-flow',
  }
}

function searchResponse() {
  return envelope({
    items: [
      {
        id: skill.id,
        slug: skill.slug,
        displayName: skill.displayName,
        summary: skill.summary,
        visibility: 'PUBLIC',
        status: 'ACTIVE',
        downloadCount: 4,
        starCount: 1,
        ratingAvg: 5,
        ratingCount: 1,
        namespace: skill.namespace,
        updatedAt: '2026-06-20T00:00:00Z',
        canSubmitPromotion: false,
        headlineVersion: { id: 52, version: skill.version, status: 'PUBLISHED' },
        publishedVersion: { id: 52, version: skill.version, status: 'PUBLISHED' },
        ownerPreviewVersion: null,
        resolutionMode: 'PUBLISHED',
      },
    ],
    total: 1,
    page: 0,
    size: 20,
  })
}

function skillDetailResponse() {
  return envelope({
    id: skill.id,
    slug: skill.slug,
    displayName: skill.displayName,
    ownerId: 'owner-1',
    ownerDisplayName: 'Owner One',
    summary: skill.summary,
    visibility: 'PUBLIC',
    status: 'ACTIVE',
    downloadCount: 4,
    starCount: 1,
    subscriptionCount: 0,
    ratingAvg: 5,
    ratingCount: 1,
    hidden: false,
    namespace: skill.namespace,
    labels: [],
    canManageLifecycle: false,
    canSubmitPromotion: false,
    canInteract: true,
    canReport: true,
    headlineVersion: { id: 52, version: skill.version, status: 'PUBLISHED' },
    publishedVersion: { id: 52, version: skill.version, status: 'PUBLISHED' },
    ownerPreviewVersion: null,
    ownerPreviewReviewComment: null,
    resolutionMode: 'PUBLISHED',
  })
}

function versionsResponse() {
  return envelope({
    items: [
      {
        id: 52,
        version: skill.version,
        status: 'PUBLISHED',
        changelog: 'initial',
        fileCount: 2,
        totalSize: 128,
        publishedAt: '2026-06-20T00:00:00Z',
        downloadAvailable: true,
      },
    ],
    total: 1,
    page: 0,
    size: 20,
  })
}

function filesResponse() {
  return envelope([
    {
      id: 201,
      filePath: 'SKILL.md',
      fileSize: 96,
      contentType: 'text/markdown',
      sha256: 'hash-skill-md',
    },
    {
      id: 202,
      filePath: 'src/main.py',
      fileSize: 32,
      contentType: 'text/x-python',
      sha256: 'hash-main-py',
    },
  ])
}

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  })
}

async function installMockApi(page: Page) {
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (!path.startsWith('/api/')) {
      await route.continue()
      return
    }

    if (path === '/api/v1/auth/me') {
      await fulfillJson(route, { detail: 'error.auth.required' }, 401)
      return
    }

    if (path === '/api/v1/auth/providers' || path === '/api/v1/auth/methods') {
      await fulfillJson(route, envelope([]))
      return
    }

    if (path === '/api/web/skills') {
      await fulfillJson(route, searchResponse())
      return
    }

    if (path === `/api/web/skills/${skill.namespace}/${skill.slug}`) {
      await fulfillJson(route, skillDetailResponse())
      return
    }

    if (path === `/api/web/skills/${skill.namespace}/${skill.slug}/versions`) {
      await fulfillJson(route, versionsResponse())
      return
    }

    if (path === `/api/web/skills/${skill.namespace}/${skill.slug}/versions/${skill.version}/files`) {
      await fulfillJson(route, filesResponse())
      return
    }

    if (path === `/api/web/skills/${skill.namespace}/${skill.slug}/versions/${skill.version}/file`) {
      await route.fulfill({
        status: 200,
        contentType: 'text/markdown',
        body: '# Browser Flow Skill\n\nMocked package documentation.\n',
      })
      return
    }

    if (path === `/api/web/skills/${skill.namespace}/${skill.slug}/versions/${skill.version}/download`) {
      await route.fulfill({
        status: 200,
        contentType: 'application/zip',
        headers: {
          'Content-Disposition': 'attachment; filename="Browser Flow Skill-1.0.0.zip"',
        },
        body: 'zip-bytes',
      })
      return
    }

    if (
      path === `/api/web/skills/${skill.id}/star`
      || path === `/api/web/skills/${skill.id}/subscription`
    ) {
      await fulfillJson(route, envelope(false))
      return
    }

    if (path === `/api/web/skills/${skill.id}/rating`) {
      await fulfillJson(route, envelope({ score: null }))
      return
    }

    if (path === `/api/web/skills/${skill.namespace}/${skill.slug}/labels`) {
      await fulfillJson(route, envelope([]))
      return
    }

    await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: path }) })
  })
}

test.describe('Browser Flow With Mock API', () => {
  test.beforeEach(async ({ page }) => {
    await setEnglishLocale(page)
    await installMockApi(page)
  })

  test('searches, opens public detail, inspects files, and triggers download', async ({ page }) => {
    await page.goto('/search?q=browser&sort=relevance&page=0&starredOnly=false')

    const card = page.getByRole('link').filter({
      has: page.getByRole('heading', { name: skill.displayName, exact: true }),
    }).first()
    await expect(card).toBeVisible()
    await card.click()

    await expect(page).toHaveURL(new RegExp(`/space/${skill.namespace}/${skill.slug}(\\?|$)`))
    await expect(page.getByRole('heading', { name: skill.displayName, exact: true }).first()).toBeVisible()
    await expect(page.getByText('Mocked package documentation.')).toBeVisible()
    await expect(page.getByText(/npx .*install/)).toBeVisible()

    await page.getByRole('tab', { name: 'Files' }).click()
    await expect(page.getByText('SKILL.md').first()).toBeVisible()
    await expect(page.getByText('src').first()).toBeVisible()

    const downloadRequest = page.waitForRequest((request) =>
      request.url().includes(`/api/web/skills/${skill.namespace}/${skill.slug}/versions/${skill.version}/download`),
    )
    await page.getByRole('button', { name: 'Download' }).click()
    await downloadRequest
  })
})

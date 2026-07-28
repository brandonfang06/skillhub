import type { Page, Request, Route } from '@playwright/test'

export function envelope(data: unknown) {
  return {
    code: 0,
    msg: 'success',
    data,
    timestamp: '2026-07-27T00:00:00Z',
    requestId: 'collection-e2e',
  }
}

const published = {
  versionId: 10,
  version: '1.4.0',
  status: 'PUBLISHED',
  draftRevision: 0,
  memberCount: 2,
  releaseNotes: 'Stable workflow',
  createdAt: '2026-07-26T00:00:00Z',
  publishedAt: '2026-07-27T00:00:00Z',
  members: [
    {
      skillId: 1,
      skillVersionId: 101,
      namespace: 'opensource',
      skillSlug: 'testing',
      version: '1.0.0',
      position: 0,
    },
    {
      skillId: 2,
      skillVersionId: 102,
      namespace: 'opensource',
      skillSlug: 'brainstorming',
      version: '2.0.0',
      position: 1,
    },
  ],
}

function detail(canCurate: boolean, withDraft: boolean) {
  return {
    collectionId: 1,
    namespace: 'opensource',
    slug: 'superpowers',
    displayName: 'Superpowers',
    summary: 'Curated agent workflows',
    status: 'ACTIVE',
    hidden: false,
    canCurate,
    latestPublishedVersion: published,
    draft: withDraft
      ? {
          ...published,
          versionId: 11,
          version: 'DRAFT',
          status: 'DRAFT',
          draftRevision: 1,
          publishedAt: null,
        }
      : null,
    createdAt: '2026-07-26T00:00:00Z',
    updatedAt: '2026-07-27T00:00:00Z',
  }
}

function summary(canCurate: boolean, withDraft: boolean) {
  const value = detail(canCurate, withDraft)
  return {
    ...value,
    latestPublishedVersion: {
      ...published,
      members: undefined,
    },
    draft: value.draft ? { ...value.draft, members: undefined } : null,
  }
}

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  })
}

export interface CollectionMockState {
  requests: Request[]
}

export async function installCollectionMockApi(
  page: Page,
  options: {
    role?: 'OWNER' | 'ADMIN' | 'MEMBER'
    platformRoles?: string[]
    canCurate?: boolean
    withDraft?: boolean
    gitlabImportEnabled?: boolean
  } = {},
): Promise<CollectionMockState> {
  const role = options.role ?? 'OWNER'
  const platformRoles = options.platformRoles ?? []
  const canCurate = options.canCurate ?? role !== 'MEMBER'
  let withDraft = options.withDraft ?? false
  const requests: Request[] = []

  await page.route('**/*', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()

    if (path === '/runtime-config.js') {
      await route.fulfill({
        contentType: 'application/javascript',
        body: `window.__SKILLHUB_RUNTIME_CONFIG__ = ${JSON.stringify({
          collectionsEnabled: 'true',
          gitlabImportEnabled: options.gitlabImportEnabled ? 'true' : 'false',
          cliNpmRegistry: 'https://nexus.example/npm-group',
          cliPackage: '@company/skillhub',
          cliVersion: '0.2.0',
        })};`,
      })
      return
    }
    if (!path.startsWith('/api/')) {
      await route.continue()
      return
    }
    requests.push(request)

    if (path === '/api/v1/auth/me') {
      await fulfillJson(
        route,
        envelope({
          userId: 'curator-1',
          displayName: 'Collection Curator',
          platformRoles,
        }),
      )
      return
    }
    if (path === '/api/v1/auth/providers' || path === '/api/v1/auth/methods') {
      await fulfillJson(route, envelope([]))
      return
    }
    if (path === '/api/web/me/namespaces') {
      await fulfillJson(
        route,
        envelope([
          {
            id: 1,
            slug: 'opensource',
            displayName: 'Open Source',
            type: 'TEAM',
            status: 'ACTIVE',
            currentUserRole: role,
            immutable: false,
            canFreeze: false,
            canUnfreeze: false,
            canArchive: false,
            canRestore: false,
            canDelete: false,
            createdAt: '2026-07-26T00:00:00Z',
          },
        ]),
      )
      return
    }
    if (path === '/api/web/namespaces/opensource') {
      await fulfillJson(
        route,
        envelope({
          id: 1,
          slug: 'opensource',
          displayName: 'Open Source',
          description: 'Internal mirror of approved open source skills',
          type: 'TEAM',
          status: 'ACTIVE',
          createdAt: '2026-07-26T00:00:00Z',
        }),
      )
      return
    }
    if (path === '/api/web/skills') {
      await fulfillJson(
        route,
        envelope({ items: [], total: 0, page: 0, size: 100 }),
      )
      return
    }
    if (
      path === '/api/web/namespaces/opensource/collections' &&
      method === 'GET'
    ) {
      await fulfillJson(
        route,
        envelope({ items: [summary(canCurate, withDraft)], total: 1 }),
      )
      return
    }
    if (
      path ===
        '/api/web/namespaces/opensource/repository-imports/preview' &&
      method === 'POST'
    ) {
      await fulfillJson(
        route,
        envelope({
          importId: 9,
          namespace: 'opensource',
          provider: 'GITLAB',
          projectId: 'oss-mirrors/superpowers',
          projectFullPath: 'oss-mirrors/superpowers',
          requestedRef: 'main',
          resolvedCommitSha: 'a'.repeat(40),
          sourceWebUrl:
            'https://gitlab.internal/oss-mirrors/superpowers',
          archiveSha256: 'b'.repeat(64),
          archiveBytes: 2048,
          state: 'PREVIEW_READY',
          candidates: [
            {
              candidateId: 31,
              sourcePath: 'skills/brainstorming',
              detectedName: 'Brainstorming',
              detectedDescription: 'Explore requirements',
              sourceVersion: '1.0.0',
              state: 'DISCOVERED',
              warnings: [],
            },
          ],
        }),
      )
      return
    }
    if (
      path === '/api/web/repository-imports/9/ingest' &&
      method === 'POST'
    ) {
      await fulfillJson(
        route,
        envelope({
          importId: 9,
          state: 'COMPLETED',
          results: [
            {
              candidateId: 31,
              state: 'CREATED',
              skillId: 301,
              skillVersionId: 401,
              versionStatus: 'PUBLISHED',
            },
          ],
        }),
      )
      return
    }
    if (
      path === '/api/web/repository-imports/9/check-updates' &&
      method === 'POST'
    ) {
      await fulfillJson(
        route,
        envelope({
          previousImportId: 9,
          changed: true,
          previousCommitSha: 'a'.repeat(40),
          currentCommitSha: 'c'.repeat(40),
          preview: {
            importId: 10,
            previousImportId: 9,
            namespace: 'opensource',
            provider: 'GITLAB',
            projectId: 'oss-mirrors/superpowers',
            projectFullPath: 'oss-mirrors/superpowers',
            requestedRef: 'main',
            resolvedCommitSha: 'c'.repeat(40),
            sourceWebUrl:
              'https://gitlab.internal/oss-mirrors/superpowers',
            archiveSha256: 'd'.repeat(64),
            archiveBytes: 2304,
            state: 'PREVIEW_READY',
            candidates: [
              {
                candidateId: 32,
                sourcePath: 'skills/brainstorming-v2',
                detectedName: 'Brainstorming',
                detectedDescription: 'Explore updated requirements',
                sourceVersion: '1.1.0',
                state: 'DISCOVERED',
                warnings: [],
              },
            ],
          },
        }),
      )
      return
    }
    if (
      path === '/api/web/repository-imports/9/collection-draft' &&
      method === 'POST'
    ) {
      await fulfillJson(
        route,
        envelope({
          collectionSlug: 'superpowers',
          draftRevision: 2,
          memberCount: 1,
        }),
      )
      return
    }
    if (
      path === '/api/web/namespaces/opensource/collections' &&
      method === 'POST'
    ) {
      if (!canCurate) {
        await fulfillJson(route, { detail: 'error.auth.forbidden' }, 403)
        return
      }
      await fulfillJson(route, envelope(detail(canCurate, false)), 201)
      return
    }
    if (path === '/api/web/collections/opensource/superpowers') {
      await fulfillJson(route, envelope(detail(canCurate, withDraft)))
      return
    }
    if (
      path === '/api/web/collections/opensource/superpowers/draft' &&
      method === 'POST'
    ) {
      withDraft = true
      await fulfillJson(route, envelope(detail(canCurate, true).draft), 201)
      return
    }
    if (
      path === '/api/web/collections/opensource/superpowers/draft' &&
      method === 'PUT'
    ) {
      await fulfillJson(route, envelope(detail(canCurate, true).draft))
      return
    }
    if (
      path === '/api/web/collections/opensource/superpowers/draft' &&
      method === 'DELETE'
    ) {
      withDraft = false
      await fulfillJson(route, envelope({ deleted: true }))
      return
    }
    if (
      path === '/api/web/collections/opensource/superpowers/publish' &&
      method === 'POST'
    ) {
      withDraft = false
      await fulfillJson(route, envelope(published))
      return
    }
    if (
      path === '/api/web/collections/opensource/superpowers/status' &&
      method === 'PUT'
    ) {
      await fulfillJson(route, envelope(detail(canCurate, withDraft)))
      return
    }
    if (path.endsWith('/versions')) {
      await fulfillJson(
        route,
        envelope({ items: [], total: 0, page: 0, size: 20 }),
      )
      return
    }

    await fulfillJson(route, { detail: path }, 404)
  })

  return { requests }
}

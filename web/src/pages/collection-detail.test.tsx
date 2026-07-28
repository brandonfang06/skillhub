import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ namespace: 'opensource', collection: 'superpowers' }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const useCollectionMock = vi.fn()
vi.mock('@/features/collection/use-collections', () => ({
  useCollection: () => useCollectionMock(),
}))

const runtimeConfigMock = vi.fn()
vi.mock('@/api/client', () => ({
  getCollectionsRuntimeConfig: () => runtimeConfigMock(),
}))

import { CollectionDetailPage } from './collection-detail'

const detail = {
  collectionId: 1,
  namespace: 'opensource',
  slug: 'superpowers',
  displayName: 'Superpowers',
  summary: 'Curated workflows',
  status: 'ACTIVE',
  hidden: false,
  canCurate: true,
  latestPublishedVersion: {
    versionId: 2,
    version: '1.4.0',
    status: 'PUBLISHED',
    draftRevision: 0,
    memberCount: 2,
    createdAt: '2026-07-27T00:00:00Z',
    publishedAt: '2026-07-27T00:00:00Z',
    members: [
      {
        skillId: 2,
        skillVersionId: 4,
        namespace: 'opensource',
        skillSlug: 'brainstorming',
        version: '2.0.0',
        position: 1,
      },
      {
        skillId: 1,
        skillVersionId: 3,
        namespace: 'opensource',
        skillSlug: 'testing',
        version: '1.0.0',
        position: 0,
      },
    ],
  },
  createdAt: '2026-07-27T00:00:00Z',
  updatedAt: '2026-07-27T00:00:00Z',
}

describe('CollectionDetailPage', () => {
  it('renders ordered published members, exact install command, and curator link', () => {
    runtimeConfigMock.mockReturnValue({
      enabled: true,
      skillhubBaseUrl: 'https://skills.example.com',
      cli: {
        npmRegistry: 'https://nexus.example/npm-group',
        packageName: '@company/skillhub',
        version: '0.2.0',
      },
    })
    useCollectionMock.mockReturnValue({ data: detail, isLoading: false })

    const html = renderToStaticMarkup(<CollectionDetailPage />)

    expect(html.indexOf('testing@1.0.0')).toBeLessThan(
      html.indexOf('brainstorming@2.0.0'),
    )
    expect(html).toContain('@company/skillhub@0.2.0')
    expect(html).toContain(
      '/dashboard/namespaces/opensource/collections/superpowers',
    )
  })

  it('does not expose unpublished collections to a non-curator', () => {
    runtimeConfigMock.mockReturnValue({ enabled: true })
    useCollectionMock.mockReturnValue({
      data: { ...detail, canCurate: false, latestPublishedVersion: null },
      isLoading: false,
    })

    expect(renderToStaticMarkup(<CollectionDetailPage />)).toContain(
      'collectionDetail.notFound',
    )
  })

  it('renders historical members whose live IDs are null', () => {
    runtimeConfigMock.mockReturnValue({
      enabled: true,
      skillhubBaseUrl: 'https://skills.example.com',
      cli: {
        npmRegistry: 'https://nexus.example/npm-group',
        packageName: '@company/skillhub',
        version: '0.2.0',
      },
    })
    useCollectionMock.mockReturnValue({
      data: {
        ...detail,
        latestPublishedVersion: {
          ...detail.latestPublishedVersion,
          memberCount: 2,
          members: [
            {
              skillId: null,
              skillVersionId: null,
              namespace: 'opensource',
              skillSlug: 'deleted-skill',
              version: '1.0.0',
              position: 0,
            },
            {
              skillId: null,
              skillVersionId: null,
              namespace: 'opensource',
              skillSlug: 'deleted-skill',
              version: '2.0.0',
              position: 1,
            },
          ],
        },
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<CollectionDetailPage />)

    expect(html).toContain('deleted-skill@1.0.0')
    expect(html).toContain('deleted-skill@2.0.0')
    expect(html).toContain('collectionDetail.degraded')
    expect(html).not.toContain('/space/opensource/deleted-skill')
    expect(html).not.toContain('@company/skillhub@0.2.0')
  })

  it('keeps a live Skill link but hides install for a deleted pinned version', () => {
    runtimeConfigMock.mockReturnValue({
      enabled: true,
      skillhubBaseUrl: 'https://skills.example.com',
      cli: {
        npmRegistry: 'https://nexus.example/npm-group',
        packageName: '@company/skillhub',
        version: '0.2.0',
      },
    })
    useCollectionMock.mockReturnValue({
      data: {
        ...detail,
        latestPublishedVersion: {
          ...detail.latestPublishedVersion,
          memberCount: 1,
          members: [
            {
              skillId: 7,
              skillVersionId: null,
              namespace: 'opensource',
              skillSlug: 'live-skill',
              version: '1.0.0',
              position: 0,
            },
          ],
        },
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<CollectionDetailPage />)

    expect(html).toContain('/space/opensource/live-skill')
    expect(html).toContain('collectionDetail.degraded')
    expect(html).not.toContain('@company/skillhub@0.2.0')
  })
})

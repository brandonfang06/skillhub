import { describe, expect, it, vi } from 'vitest'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ namespace: 'global' }),
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  }
})

vi.mock('@/features/namespace/namespace-header', () => ({
  NamespaceHeader: () => null,
}))

vi.mock('@/features/skill/skill-card', () => ({
  SkillCard: () => null,
}))

vi.mock('@/features/collection/collection-card', () => ({
  CollectionCard: () => null,
}))

vi.mock('@/shared/components/skeleton-loader', () => ({
  SkeletonList: () => null,
}))

vi.mock('@/shared/components/empty-state', () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}))

const useNamespaceDetailMock = vi.fn()
vi.mock('@/shared/hooks/use-namespace-queries', () => ({
  useNamespaceDetail: () => useNamespaceDetailMock(),
}))

const useSearchSkillsMock = vi.fn((_params: unknown) => ({
    data: { items: [] },
    isLoading: false,
  }))
vi.mock('@/shared/hooks/use-skill-queries', () => ({
  useSearchSkills: (params: unknown) => useSearchSkillsMock(params),
}))

const useCollectionsMock = vi.fn((_namespace: string, _enabled: boolean) => ({
  data: { items: [], total: 0 },
  isLoading: false,
}))
vi.mock('@/features/collection/use-collections', () => ({
  useCollections: (namespace: string, enabled: boolean) =>
    useCollectionsMock(namespace, enabled),
}))

const runtimeConfigMock = vi.fn(() => ({ enabled: false }))
vi.mock('@/api/client', () => ({
  getCollectionsRuntimeConfig: () => runtimeConfigMock(),
}))

import { renderToStaticMarkup } from 'react-dom/server'
import { NamespacePage } from './namespace'

describe('NamespacePage', () => {
  it('exports a named component function', () => {
    expect(typeof NamespacePage).toBe('function')
  })

  it('renders the not-found state when namespace data is missing', () => {
    useNamespaceDetailMock.mockReturnValue({
      data: null,
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespacePage />)
    expect(html).toContain('namespace.notFound')
  })

  it('keeps the existing skill surface when collections are disabled', () => {
    runtimeConfigMock.mockReturnValue({ enabled: false })
    useNamespaceDetailMock.mockReturnValue({
      data: { slug: 'global', displayName: 'Global' },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespacePage />)

    expect(html).toContain('namespace.skillList')
    expect(html).not.toContain('namespace.collectionList')
    expect(useSearchSkillsMock).toHaveBeenCalledWith({
      namespace: 'global',
      page: 0,
      size: 20,
    })
    expect(useCollectionsMock).toHaveBeenCalledWith('global', false)
  })

  it('adds a separate collection tab without enabling its query by default', () => {
    runtimeConfigMock.mockReturnValue({ enabled: true })
    useNamespaceDetailMock.mockReturnValue({
      data: { slug: 'global', displayName: 'Global' },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespacePage />)

    expect(html).toContain('namespace.skillsTab')
    expect(html).toContain('namespace.collectionsTab')
    expect(useCollectionsMock).toHaveBeenCalledWith('global', false)
  })
})

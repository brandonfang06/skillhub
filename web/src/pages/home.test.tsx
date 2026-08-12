import { beforeEach, describe, expect, it, vi } from 'vitest'

// HomePage is a component-only page. We verify it exports correctly
// and renders key sections.

const navigateMock = vi.fn()
let searchBarProps: { onSearch?: (query: string) => void } = {}

vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigateMock }))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  }
})

vi.mock('@/features/search/search-bar', () => ({
  SearchBar: (props: { onSearch?: (query: string) => void }) => {
    searchBarProps = props
    return null
  },
}))

vi.mock('@/features/search/namespace-search-filter', () => ({
  NamespaceSearchFilter: () => null,
}))

vi.mock('@/features/skill/skill-card', () => ({
  SkillCard: () => null,
}))

vi.mock('@/shared/components/skeleton-loader', () => ({
  SkeletonList: () => null,
}))

vi.mock('@/shared/components/quick-start', () => ({
  QuickStartSection: () => null,
}))

vi.mock('@/shared/hooks/use-skill-queries', () => ({
  useSearchSkills: () => ({
    data: { items: [] },
    isLoading: false,
  }),
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children }: { children: unknown }) => children,
}))

import { renderToStaticMarkup } from 'react-dom/server'
import { HomePage } from './home'

describe('HomePage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    searchBarProps = {}
  })

  it('exports a named component function', () => {
    expect(typeof HomePage).toBe('function')
  })

  it('renders the hero section with brand name', () => {
    const html = renderToStaticMarkup(<HomePage />)

    expect(html).toContain('SkillHub')
    expect(html).toContain('home.subtitle')
  })

  it('gives a typed namespace precedence when navigating to Search', () => {
    renderToStaticMarkup(<HomePage />)

    searchBarProps.onSearch?.('@team-ai review')

    expect(navigateMock).toHaveBeenCalledWith({
      to: '/search',
      search: { q: 'review', namespace: 'team-ai', sort: 'relevance', page: 0, starredOnly: false },
    })
  })
})

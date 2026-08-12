import { beforeEach, describe, expect, it, vi } from 'vitest'

const navigateMock = vi.fn()
let searchBarProps: { onSearch?: (query: string) => void } = {}

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: unknown }) => children,
  useNavigate: () => navigateMock,
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

vi.mock('lucide-react', () => ({
  PackageOpen: () => null,
  Terminal: () => null,
  Shield: () => null,
  Users: () => null,
  GitBranch: () => null,
  Search: () => null,
  Settings: () => null,
}))

vi.mock('@/shared/components/landing-quick-start', () => ({
  LandingQuickStartSection: () => null,
}))

vi.mock('@/features/skill/skill-card', () => ({
  SkillCard: () => null,
}))

vi.mock('@/features/search/search-bar', () => ({
  SearchBar: (props: { onSearch?: (query: string) => void }) => {
    searchBarProps = props
    return null
  },
}))

vi.mock('@/features/search/namespace-search-filter', () => ({
  NamespaceSearchFilter: () => null,
}))

vi.mock('@/shared/components/skeleton-loader', () => ({
  SkeletonList: () => null,
}))

vi.mock('@/shared/hooks/use-skill-queries', () => ({
  useSearchSkills: () => ({
    data: { items: [] },
    isLoading: false,
  }),
}))

vi.mock('@/shared/hooks/use-in-view', () => ({
  useInView: () => ({ ref: vi.fn(), inView: true }),
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children }: { children: unknown }) => children,
}))

import { renderToStaticMarkup } from 'react-dom/server'
import { LandingPage } from './landing'

describe('LandingPage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    searchBarProps = {}
  })

  it('exports a named component function', () => {
    expect(typeof LandingPage).toBe('function')
  })

  it('renders the brand name in the hero section', () => {
    const html = renderToStaticMarkup(<LandingPage />)

    expect(html).toContain('SkillHub')
    expect(html).toContain('landing.hero.title')
  })

  it('keeps typed namespace search compatible for anonymous users', () => {
    renderToStaticMarkup(<LandingPage />)

    searchBarProps.onSearch?.('@public-tools agent')

    expect(navigateMock).toHaveBeenCalledWith({
      to: '/search',
      search: { q: 'agent', namespace: 'public-tools', sort: 'relevance', page: 0, starredOnly: false },
    })
  })
})

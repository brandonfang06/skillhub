import { beforeEach, describe, expect, it, vi } from 'vitest'

const linkProps = vi.hoisted(() => [] as Array<Record<string, unknown>>)
const useMySkillsMock = vi.hoisted(() => vi.fn())

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, ...props }: { children: unknown; [key: string]: unknown }) => {
    linkProps.push(props)
    return children
  },
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

vi.mock('@/features/auth/use-auth', () => ({
  useAuth: () => ({
    user: { userId: 'u1', displayName: 'Test User', platformRoles: ['USER'] },
  }),
}))

vi.mock('@/shared/hooks/use-user-queries', () => ({
  useMySkills: useMySkillsMock,
}))

vi.mock('@/shared/lib/governance-access', () => ({
  canViewGovernanceCenter: () => false,
}))

vi.mock('@/shared/lib/skill-lifecycle', () => ({
  getHeadlineVersion: () => null,
}))

vi.mock('@/features/token/token-list', () => ({
  TokenList: () => null,
}))

vi.mock('@/shared/ui/card', () => ({
  Card: ({ children }: { children: unknown }) => children,
  CardContent: ({ children }: { children: unknown }) => children,
  CardDescription: ({ children }: { children: unknown }) => children,
  CardHeader: ({ children }: { children: unknown }) => children,
  CardTitle: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/app/page-shell-style', () => ({
  APP_SHELL_PAGE_CLASS_NAME: 'page-shell',
}))

import { renderToStaticMarkup } from 'react-dom/server'
import { DashboardPage } from './dashboard'

beforeEach(() => {
  linkProps.length = 0
  useMySkillsMock.mockReturnValue({
    data: { items: [], total: 0, page: 0, size: 5 },
    isLoading: false,
  })
})

describe('DashboardPage', () => {
  it('exports a named component function', () => {
    expect(typeof DashboardPage).toBe('function')
  })

  it('renders the dashboard title and user info section', () => {
    const html = renderToStaticMarkup(<DashboardPage />)

    expect(html).toContain('dashboard.title')
    expect(html).toContain('dashboard.userInfo')
  })

  it('shows the my-skills preview section', () => {
    const html = renderToStaticMarkup(<DashboardPage />)

    expect(html).toContain('mySkills.title')
  })

  it('passes an unencoded slug to the named skill route', () => {
    useMySkillsMock.mockReturnValue({
      data: {
        items: [{
          id: 1,
          namespace: 'team-ai',
          slug: 'skill%name',
          displayName: 'Skill name',
        }],
        total: 1,
        page: 0,
        size: 5,
      },
      isLoading: false,
    })

    renderToStaticMarkup(<DashboardPage />)

    expect(linkProps).toContainEqual(expect.objectContaining({
      to: '/space/$namespace/$slug',
      params: { namespace: 'team-ai', slug: 'skill%name' },
    }))
  })
})

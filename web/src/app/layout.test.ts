import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const linkProps = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@tanstack/react-router', () => ({
  Outlet: () => null,
  Link: ({ children, ...props }: { children: unknown; [key: string]: unknown }) => {
    linkProps.push(props)
    return children
  },
  useRouterState: () => ({ pathname: '/', resolvedPathname: '/' }),
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: { language: 'en' },
    }),
  }
})

vi.mock('@/features/auth/use-auth', () => ({
  useAuth: () => ({
    user: null,
    isLoading: false,
  }),
}))

vi.mock('@/shared/components/language-switcher', () => ({
  LanguageSwitcher: () => null,
}))

vi.mock('@/shared/components/user-menu', () => ({
  UserMenu: () => null,
}))

vi.mock('@/features/notification/notification-bell', () => ({
  NotificationBell: () => null,
}))

vi.mock('./layout-header-style', () => ({
  getAppHeaderClassName: () => 'header-class',
}))

vi.mock('./layout-main-content', () => ({
  resolveAppMainContentPathname: (p: string) => p,
  getAppMainContentLayout: () => ({
    mainClassName: 'main-class',
    contentClassName: 'content-class',
  }),
}))

import { Layout } from './layout'

beforeEach(() => {
  linkProps.length = 0
})

describe('Layout', () => {
  it('exports a named Layout component function', () => {
    expect(typeof Layout).toBe('function')
    expect(Layout.name).toBe('Layout')
  })

  it('does not render the deprecated external resources footer links', () => {
    const html = renderToStaticMarkup(createElement(Layout))

    expect(html).not.toContain('landing.footerDocs')
    expect(html).not.toContain('landing.footerGithub')
    expect(html).not.toContain('landing.footerCommunity')
    expect(html).not.toContain('Resources')
    expect(html).not.toContain('Documentation')
    expect(html).not.toContain('API')
    expect(html).not.toContain('Community')
    expect(html).not.toContain('footer.copyright')
    expect(html).not.toContain('footer.privacy')
    expect(html).not.toContain('footer.terms')
    expect(html).not.toContain('Privacy Policy')
    expect(html).not.toContain('Terms of Service')
  })

  it('links anonymous users to login without an empty return target', () => {
    renderToStaticMarkup(createElement(Layout))

    expect(linkProps).toContainEqual(expect.objectContaining({ to: '/login' }))
    expect(linkProps.find((props) => props.to === '/login')).not.toHaveProperty('search')
  })
})

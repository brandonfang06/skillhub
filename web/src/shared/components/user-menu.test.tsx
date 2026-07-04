import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import * as mod from './user-menu'
import { UserMenu } from './user-menu'

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react')
  return {
    ...actual,
    useState: (initialValue: unknown) => [
      typeof initialValue === 'boolean' ? true : initialValue,
      vi.fn(),
    ],
  }
})

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  }
})

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    className,
    onClick,
    to,
  }: {
    children: ReactNode
    className?: string
    onClick?: () => void
    to: string
  }) => (
    <a
      href={to}
      className={className}
      onClick={(event) => {
        event.preventDefault()
        onClick?.()
      }}
    >
      {children}
    </a>
  ),
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    setQueryData: vi.fn(),
  }),
}))

vi.mock('@/api/client', () => ({
  authApi: {
    logout: vi.fn(),
  },
}))

vi.mock('@/shared/hooks/use-namespace-queries', () => ({
  useMyNamespaces: () => ({ data: [] }),
}))

describe('user-menu module exports', () => {
  it('exports the UserMenu component', () => {
    expect(mod.UserMenu).toBeTypeOf('function')
  })
})

describe('UserMenu security settings visibility', () => {
  it('shows security settings when password changes are allowed, independent of OAuth provider', () => {
    const html = renderToStaticMarkup(
      <UserMenu
        user={{
          displayName: 'OAuth Linked User',
          oauthProvider: 'github',
          platformRoles: ['USER'],
          canChangePassword: true,
        }}
      />,
    )

    expect(html).toContain('user.menu.security')
  })

  it('hides security settings when password changes are not allowed, even for a local-looking account', () => {
    const html = renderToStaticMarkup(
      <UserMenu
        user={{
          displayName: 'Local User',
          platformRoles: ['USER'],
          canChangePassword: false,
        }}
      />,
    )

    expect(html).not.toContain('user.menu.security')
  })
})

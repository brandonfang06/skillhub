import { describe, expect, it, vi } from 'vitest'

const runtimeConfigMock = vi.hoisted(() => ({
  localRegistrationEnabled: true,
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: unknown }) => children,
  useNavigate: () => vi.fn(),
  useSearch: () => ({ returnTo: '' }),
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: { resolvedLanguage: 'en' },
    }),
  }
})

vi.mock('lucide-react', () => ({
  Eye: () => null,
  EyeOff: () => null,
}))

vi.mock('@/api/client', () => ({
  getDirectAuthRuntimeConfig: () => ({ enabled: false }),
  getLocalRegistrationRuntimeConfig: () => ({ enabled: runtimeConfigMock.localRegistrationEnabled }),
}))

vi.mock('@/features/auth/login-button', () => ({
  LoginButton: () => null,
}))

vi.mock('@/features/auth/session-bootstrap-entry', () => ({
  SessionBootstrapEntry: () => null,
}))

vi.mock('@/features/auth/use-auth-methods', () => ({
  useAuthMethods: () => ({ data: [] }),
}))

vi.mock('@/features/auth/use-password-login', () => ({
  usePasswordLogin: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/shared/ui/input', () => ({
  Input: () => null,
}))

vi.mock('@/shared/ui/tabs', () => ({
  Tabs: ({ children }: { children: unknown }) => children,
  TabsContent: ({ children }: { children: unknown }) => children,
  TabsList: ({ children }: { children: unknown }) => children,
  TabsTrigger: ({ children }: { children: unknown }) => children,
}))

import { renderToStaticMarkup } from 'react-dom/server'
import { LoginPage } from './login'

describe('LoginPage', () => {
  it('exports a named component function', () => {
    expect(typeof LoginPage).toBe('function')
  })

  it('renders the login title and form elements', () => {
    runtimeConfigMock.localRegistrationEnabled = true
    const html = renderToStaticMarkup(<LoginPage />)

    expect(html).toContain('login.title')
    expect(html).toContain('login.subtitle')
    expect(html).toContain('login.submit')
    expect(html).toContain('login.register')
  })

  it('hides the registration link when local registration is disabled', () => {
    runtimeConfigMock.localRegistrationEnabled = false

    const html = renderToStaticMarkup(<LoginPage />)

    expect(html).not.toContain('login.register')
  })
})

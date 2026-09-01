import { describe, expect, it, vi } from 'vitest'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
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

vi.mock('@/shared/ui/card', () => ({
  Card: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/api/client', () => ({
  getCurrentUser: vi.fn().mockResolvedValue(null),
  tokenApi: { createToken: vi.fn() },
}))

vi.mock('@/app/router', () => ({
  ORIGINAL_URL_SEARCH: '',
}))

import {
  buildCliRedirectUrl,
  CliAuthPage,
  getCliAuthRegistryUrl,
  resolveLoopbackRedirectUri,
} from './cli-auth'

describe('resolveLoopbackRedirectUri', () => {
  it.each([
    'http://localhost:4312/callback?source=cli',
    'http://127.0.0.1:4312/callback',
    'http://[::1]:4312/callback',
  ])('accepts an HTTP loopback callback: %s', (uri) => {
    expect(resolveLoopbackRedirectUri(uri)?.href).toBe(uri)
  })

  it.each([
    'https://localhost:4312/callback',
    'http://localhost.example.com/callback',
    'http://example.com/callback',
    'http://user:password@localhost:4312/callback',
    'javascript:alert(1)',
    'not-a-url',
  ])('rejects a non-loopback or unsafe callback: %s', (uri) => {
    expect(resolveLoopbackRedirectUri(uri)).toBeNull()
  })

  it('removes an attacker-provided fragment', () => {
    expect(resolveLoopbackRedirectUri(
      'http://localhost:4312/callback?source=cli#attacker',
    )?.href).toBe('http://localhost:4312/callback?source=cli')
  })
})

describe('buildCliRedirectUrl', () => {
  it('preserves callback query parameters and replaces the fragment with encoded credentials', () => {
    const target = resolveLoopbackRedirectUri(
      'http://localhost:4312/callback?source=cli#attacker',
    )
    expect(target).not.toBeNull()

    const result = new URL(buildCliRedirectUrl(target!, {
      token: 'skillhub token&secret',
      registry: 'https://example.com/skillhub',
      state: 'state/value',
    }))

    expect(result.search).toBe('?source=cli')
    expect(result.hash).not.toContain('attacker')
    expect(new URLSearchParams(result.hash.slice(1))).toEqual(
      new URLSearchParams({
        token: 'skillhub token&secret',
        registry: 'https://example.com/skillhub',
        state: 'state/value',
      }),
    )
  })
})

describe('CliAuthPage', () => {
  it('exports a named component function', () => {
    expect(typeof CliAuthPage).toBe('function')
    expect(CliAuthPage.name).toBe('CliAuthPage')
  })

  it('returns the configured CLI registry including its path prefix', () => {
    const originalWindow = globalThis.window
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      writable: true,
      value: {
        __SKILLHUB_RUNTIME_CONFIG__: {
          appBaseUrl: 'https://ai-coding-platform.tsmc.com/skillhub',
          cliRegistryUrl: 'http://skillhub-test.ftest.tsmc.com',
        },
        location: { origin: 'https://ai-coding-platform.tsmc.com' },
      },
    })

    try {
      expect(getCliAuthRegistryUrl()).toBe('http://skillhub-test.ftest.tsmc.com')
    } finally {
      if (originalWindow) {
        Object.defineProperty(globalThis, 'window', {
          configurable: true,
          writable: true,
          value: originalWindow,
        })
      } else {
        Reflect.deleteProperty(globalThis, 'window')
      }
    }
  })
})

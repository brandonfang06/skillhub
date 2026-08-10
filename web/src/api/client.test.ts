import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const originalWindow = globalThis.window
const originalDocument = globalThis.document

function setMockWindow(runtimeConfig?: Window['__SKILLHUB_RUNTIME_CONFIG__']) {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: {
      __SKILLHUB_RUNTIME_CONFIG__: runtimeConfig,
    } satisfies Pick<Window, '__SKILLHUB_RUNTIME_CONFIG__'>,
  })
}

// Mock i18n before importing client
vi.mock('@/i18n/config', () => ({
  default: { resolvedLanguage: 'en' },
}))

// Mock api-error before importing client
vi.mock('@/shared/lib/api-error', () => ({
  ApiError: class ApiError extends Error {
    status: number
    serverMessage?: string
    serverMessageKey?: string
    requestId?: string
    serverMessageArgs: string[]
    constructor(
      message: string,
      status: number,
      serverMessage?: string,
      serverMessageKey?: string,
      requestId?: string,
      serverMessageArgs: string[] = [],
    ) {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.serverMessage = serverMessage
      this.serverMessageKey = serverMessageKey
      this.requestId = requestId
      this.serverMessageArgs = serverMessageArgs
    }
  },
  handleApiError: vi.fn(),
}))

import {
  WEB_API_PREFIX,
  adminApi,
  authApi,
  buildApiUrl,
  fetchJson,
  fetchText,
  getDirectAuthRuntimeConfig,
  getLocalRegistrationRuntimeConfig,
  getPlaygroundRuntimeConfig,
  getSessionBootstrapRuntimeConfig,
  namespaceApi,
  reviewApi,
  skillLifecycleApi,
} from './client'

beforeEach(() => {
  setMockWindow()
})

afterEach(() => {
  vi.unstubAllGlobals()

  if (originalDocument) {
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      writable: true,
      value: originalDocument,
    })
  } else {
    Reflect.deleteProperty(globalThis, 'document')
  }

  if (originalWindow) {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      writable: true,
      value: originalWindow,
    })
    return
  }

  Reflect.deleteProperty(globalThis, 'window')
})

describe('WEB_API_PREFIX', () => {
  it('uses the /api/web prefix for web-facing endpoints', () => {
    expect(WEB_API_PREFIX).toBe('/api/web')
  })
})

describe('getPlaygroundRuntimeConfig', () => {
  it('keeps playground disabled when runtime config is absent', () => {
    setMockWindow()

    expect(getPlaygroundRuntimeConfig()).toEqual({ enabled: false })
  })

  it('returns a normalized sidecar URL only when playground is enabled', () => {
    setMockWindow({
      playgroundEnabled: 'true',
      playgroundBaseUrl: 'http://localhost:8091/',
    })

    expect(getPlaygroundRuntimeConfig()).toEqual({
      enabled: true,
      baseUrl: 'http://localhost:8091',
    })
  })

  it('disables playground when enabled has no base URL', () => {
    setMockWindow({ playgroundEnabled: 'true', playgroundBaseUrl: '' })

    expect(getPlaygroundRuntimeConfig()).toEqual({ enabled: false })
  })
})

describe('buildApiUrl', () => {
  it('returns the path as-is when no runtime base URL is configured', () => {
    expect(buildApiUrl('/api/v1/auth/me')).toBe('/api/v1/auth/me')
  })

  it('prepends the runtime base URL when one is set', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { apiBaseUrl: 'https://api.example.com' }
    const url = buildApiUrl('/api/v1/auth/me')
    expect(url).toBe('https://api.example.com/api/v1/auth/me')
  })

  it('handles a trailing slash on the base URL', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { apiBaseUrl: 'https://api.example.com/' }
    const url = buildApiUrl('/api/v1/auth/me')
    expect(url).toBe('https://api.example.com/api/v1/auth/me')
  })

  it('preserves base URL path prefixes', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { apiBaseUrl: 'https://api.example.com/skill_hub' }
    const url = buildApiUrl('/api/v1/auth/me')
    expect(url).toBe('https://api.example.com/skill_hub/api/v1/auth/me')
  })

  it('supports relative base URL path prefixes', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { apiBaseUrl: '/skill_hub' }
    const url = buildApiUrl('/api/v1/auth/me')
    expect(url).toBe('/skill_hub/api/v1/auth/me')
  })
})

describe('authApi.logout', () => {
  it('uses the runtime application base path', async () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { basePath: '/skillhub' }
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      writable: true,
      value: { cookie: '' },
    })
    const fetchMock = vi.fn().mockResolvedValue({ status: 204 })
    vi.stubGlobal('fetch', fetchMock)

    await authApi.logout()

    expect(fetchMock).toHaveBeenCalledWith(
      '/skillhub/api/v1/auth/logout',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})

describe('fetchText', () => {
  it('applies base URL path prefixes for fetch requests', async () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { apiBaseUrl: 'https://api.example.com/skill_hub' }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => 'ok',
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchText('/api/v1/auth/me')

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/skill_hub/api/v1/auth/me',
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    )
  })

  it('preserves structured error details for failed text requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({
        detail: 'error.auth.required',
        requestId: 'readme-401',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchText('/api/web/skills/global/demo/versions/1.0.0/file?path=SKILL.md'))
      .rejects.toMatchObject({
        name: 'ApiError',
        status: 401,
        serverMessage: 'error.auth.required',
        serverMessageKey: 'error.auth.required',
        requestId: 'readme-401',
      })
  })

  it('preserves the status when a failed text response is not JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => {
        throw new SyntaxError('not json')
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchText('/api/web/skills/global/demo/versions/1.0.0/file?path=SKILL.md'))
      .rejects.toMatchObject({ name: 'ApiError', status: 503 })
  })
})

describe('namespaceApi.delete', () => {
  it('sends a DELETE request to the normalized namespace endpoint', async () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { apiBaseUrl: 'https://api.example.com' }
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      writable: true,
      value: {
        cookie: 'XSRF-TOKEN=test-token',
      },
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 0,
        msg: 'ok',
        data: null,
        timestamp: '2026-05-07T00:00:00Z',
        requestId: 'req-test',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await namespaceApi.delete('@team-delete')

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/api/web/namespaces/team-delete',
      expect.objectContaining({
        method: 'DELETE',
        headers: expect.any(Headers),
      }),
    )
  })
})

describe('fetchJson errors', () => {
  it('preserves structured denial arguments and request ID', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({
        code: 403,
        msg: 'error.apiToken.scope.missing',
        data: { args: ['skill:publish'] },
        timestamp: '2026-07-30T00:00:00Z',
        requestId: 'scope-request',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchJson('/api/v1/skills')).rejects.toMatchObject({
      status: 403,
      serverMessageKey: 'error.apiToken.scope.missing',
      requestId: 'scope-request',
      serverMessageArgs: ['skill:publish'],
    })
  })
})

describe('skillLifecycleApi.updateVisibility', () => {
  it('patches the normalized web endpoint with JSON and CSRF headers', async () => {
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      writable: true,
      value: {
        cookie: 'XSRF-TOKEN=test-token',
      },
    })
    const response = {
      skillId: 101,
      visibility: 'NAMESPACE_ONLY' as const,
      changed: true,
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 0,
        msg: 'ok',
        data: response,
        timestamp: '2026-07-27T00:00:00Z',
        requestId: 'req-test',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      skillLifecycleApi.updateVisibility('@team-ai', 'demo skill', 'NAMESPACE_ONLY'),
    ).resolves.toEqual(response)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/web/skills/team-ai/demo%20skill/visibility',
      expect.objectContaining({
        method: 'PATCH',
        headers: expect.any(Headers),
        body: JSON.stringify({ visibility: 'NAMESPACE_ONLY' }),
      }),
    )
    const request = fetchMock.mock.calls[0]?.[1]
    expect(request?.headers.get('Content-Type')).toBe('application/json')
    expect(request?.headers.get('X-XSRF-TOKEN')).toBe('test-token')
  })
})

describe('reviewApi.batchDecision', () => {
  it('sends one POST request with the selected review tasks', async () => {
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      writable: true,
      value: {
        cookie: 'XSRF-TOKEN=test-token',
      },
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 0,
        msg: 'ok',
        data: {
          totalCount: 2,
          successCount: 2,
          failureCount: 0,
          results: [],
        },
        timestamp: '2026-07-16T00:00:00Z',
        requestId: 'req-test',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await reviewApi.batchDecision({
      reviewTaskIds: [11, 12],
      decision: 'REJECT',
      comment: 'Needs changes',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/web/reviews/batch-decision',
      expect.objectContaining({
        method: 'POST',
        headers: expect.any(Headers),
        body: JSON.stringify({
          reviewTaskIds: [11, 12],
          decision: 'REJECT',
          comment: 'Needs changes',
        }),
      }),
    )
  })
})

describe('adminApi.getDownloadEvents', () => {
  it('passes filters through to the admin download event endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        code: 0,
        msg: 'ok',
        data: {
          items: [],
          total: 0,
          page: 1,
          size: 10,
        },
        timestamp: '2026-07-09T00:00:00Z',
        requestId: 'req-test',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await adminApi.getDownloadEvents({
      namespace: 'team-a',
      slug: 'demo',
      userId: 'user-a',
      userQuery: 'User A',
      source: 'web',
      startTime: '2026-07-01T00:00:00.000Z',
      endTime: '2026-07-09T23:59:59.000Z',
      page: 1,
      size: 10,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/download-events?namespace=team-a&slug=demo&userId=user-a&userQuery=User+A&source=web&startTime=2026-07-01T00%3A00%3A00.000Z&endTime=2026-07-09T23%3A59%3A59.000Z&page=1&size=10',
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    )
  })

  it('builds a filtered CSV export URL without pagination', () => {
    const url = adminApi.buildDownloadEventsCsvUrl({
      namespace: 'team-a',
      slug: 'demo',
      version: '1.0.0',
      userId: 'user-a',
      userQuery: 'User A',
      source: 'cli',
      startTime: '2026-07-01T00:00:00.000Z',
      endTime: '2026-07-09T23:59:59.000Z',
    })

    expect(url).toBe(
      '/api/v1/admin/download-events.csv?namespace=team-a&slug=demo&version=1.0.0&userId=user-a&userQuery=User+A&source=cli&startTime=2026-07-01T00%3A00%3A00.000Z&endTime=2026-07-09T23%3A59%3A59.000Z',
    )
    expect(url).not.toContain('page=')
    expect(url).not.toContain('size=')
  })
})

describe('getDirectAuthRuntimeConfig', () => {
  it('returns disabled when no runtime config is present', () => {
    const config = getDirectAuthRuntimeConfig()
    expect(config.enabled).toBe(false)
    expect(config.provider).toBeUndefined()
  })

  it('returns enabled with provider when both flag and provider are set', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = {
      authDirectEnabled: 'true',
      authDirectProvider: 'ldap',
    }
    const config = getDirectAuthRuntimeConfig()
    expect(config.enabled).toBe(true)
    expect(config.provider).toBe('ldap')
  })

  it('returns disabled when the flag is true but the provider is missing', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = {
      authDirectEnabled: 'true',
    }
    const config = getDirectAuthRuntimeConfig()
    expect(config.enabled).toBe(false)
  })

  it('returns disabled when the flag is false', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = {
      authDirectEnabled: 'false',
      authDirectProvider: 'ldap',
    }
    const config = getDirectAuthRuntimeConfig()
    expect(config.enabled).toBe(false)
  })

  it('treats various truthy flag values correctly', () => {
    for (const flag of ['1', 'yes', 'on', 'TRUE', ' True ']) {
      window.__SKILLHUB_RUNTIME_CONFIG__ = {
        authDirectEnabled: flag,
        authDirectProvider: 'ldap',
      }
      expect(getDirectAuthRuntimeConfig().enabled).toBe(true)
    }
  })
})

describe('getLocalRegistrationRuntimeConfig', () => {
  it('defaults local registration to enabled', () => {
    expect(getLocalRegistrationRuntimeConfig().enabled).toBe(true)
  })

  it('can disable local registration through runtime config', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = {
      localRegistrationEnabled: 'false',
    }

    expect(getLocalRegistrationRuntimeConfig().enabled).toBe(false)
  })
})

describe('getSessionBootstrapRuntimeConfig', () => {
  it('returns disabled when no runtime config is present', () => {
    const config = getSessionBootstrapRuntimeConfig()
    expect(config.enabled).toBe(false)
    expect(config.auto).toBe(false)
    expect(config.provider).toBeUndefined()
  })

  it('returns fully enabled config when all flags and provider are set', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = {
      authSessionBootstrapEnabled: '1',
      authSessionBootstrapProvider: 'sso',
      authSessionBootstrapAuto: 'true',
    }
    const config = getSessionBootstrapRuntimeConfig()
    expect(config.enabled).toBe(true)
    expect(config.provider).toBe('sso')
    expect(config.auto).toBe(true)
  })

  it('returns disabled when the provider is blank', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = {
      authSessionBootstrapEnabled: 'true',
      authSessionBootstrapProvider: '  ',
    }
    const config = getSessionBootstrapRuntimeConfig()
    expect(config.enabled).toBe(false)
  })
})

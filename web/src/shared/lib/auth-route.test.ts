import { describe, expect, it, vi } from 'vitest'
import { isRedirect } from '@tanstack/react-router'
import { buildReturnTo, createRequireAuth } from './auth-route'

describe('auth-route', () => {
  it('buildReturnTo preserves pathname search and hash', () => {
    expect(buildReturnTo({
      pathname: '/space/global/caldav-calendar',
      searchStr: '?tab=files',
      hash: '#readme',
    })).toBe('/space/global/caldav-calendar?tab=files#readme')
  })

  it('removes the runtime application base from browser return targets', () => {
    const originalWindow = globalThis.window
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      writable: true,
      value: { __SKILLHUB_RUNTIME_CONFIG__: { basePath: '/skillhub' } },
    })

    try {
      expect(buildReturnTo({
        pathname: '/skillhub/dashboard/reviews/13',
        searchStr: '?tab=pending',
        hash: '#panel',
      })).toBe('/dashboard/reviews/13?tab=pending#panel')
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

  it('createRequireAuth redirects unauthenticated users to login with returnTo', async () => {
    const requireAuth = createRequireAuth(async () => null)

    await expect(requireAuth({
      location: {
        pathname: '/space/global/caldav-calendar',
        searchStr: '?tab=files',
        hash: '#readme',
      },
    })).rejects.toSatisfy((error: unknown) => {
      expect(isRedirect(error)).toBe(true)
      if (!isRedirect(error)) {
        return false
      }
      expect(error.options.to).toBe('/login')
      expect(error.options.search).toEqual({
        returnTo: '/space/global/caldav-calendar?tab=files#readme',
      })
      return true
    })
  })

  it('createRequireAuth returns the current user when authenticated', async () => {
    const user = { userId: 'user-1' }
    const getCurrentUser = vi.fn(async () => user)
    const requireAuth = createRequireAuth(getCurrentUser)

    await expect(requireAuth({
      location: { pathname: '/dashboard' },
    })).resolves.toEqual({ user })
    expect(getCurrentUser).toHaveBeenCalledTimes(1)
  })
})

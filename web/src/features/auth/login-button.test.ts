import { describe, expect, it } from 'vitest'
import * as loginButton from './login-button'

/**
 * LoginButton is a React component that renders OAuth login buttons from backend-provided
 * auth methods. It filters for OAUTH_REDIRECT method types and shows a loading state.
 * There are no exported pure functions, constants, or data transformations to unit-test.
 *
 * Full rendering tests would require a React test renderer, QueryClient provider,
 * and i18next setup. This file verifies the export surface.
 */
describe('login-button module exports', () => {
  it('exports LoginButton component', () => {
    expect(loginButton.LoginButton).toBeTypeOf('function')
  })

  it('builds provider assets and OAuth actions below the runtime base path', () => {
    const originalWindow = globalThis.window
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      writable: true,
      value: { __SKILLHUB_RUNTIME_CONFIG__: { basePath: '/skillhub' } },
    })

    try {
      expect(loginButton.getOAuthIconUrl('Keycloak')).toBe('/skillhub/keycloak-logo.svg')
      expect(loginButton.getOAuthActionUrl('/oauth2/authorization/keycloak')).toBe(
        '/skillhub/oauth2/authorization/keycloak',
      )
      expect(loginButton.getOAuthActionUrl('/skillhub/oauth2/authorization/keycloak')).toBe(
        '/skillhub/oauth2/authorization/keycloak',
      )
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

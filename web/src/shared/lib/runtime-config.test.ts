import { afterEach, describe, expect, it } from 'vitest'
import {
  buildAppPath,
  getApiBaseUrl,
  getAppBasePath,
  normalizeBasePath,
  toAppRelativePath,
} from './runtime-config'

const originalWindow = globalThis.window

function setRuntimeConfig(config: Record<string, string> = {}) {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: { __SKILLHUB_RUNTIME_CONFIG__: config },
  })
}

afterEach(() => {
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

describe('normalizeBasePath', () => {
  it.each([
    [undefined, ''],
    ['', ''],
    ['/', ''],
    ['/skillhub', '/skillhub'],
    ['/skillhub/', '/skillhub'],
  ])('normalizes %s to %s', (input, expected) => {
    expect(normalizeBasePath(input)).toBe(expected)
  })

  it.each([
    'skillhub',
    '//evil.example',
    '/skillhub?next=/admin',
    '/skillhub#admin',
    '/skillhub/../admin',
    '/skillhub/%2e%2e/admin',
    '/skill hub',
    '/skillhub;admin',
    '/skillhub//',
    '/skillhub//admin',
  ])('rejects unsafe base path %s', (input) => {
    expect(() => normalizeBasePath(input)).toThrow('Invalid SkillHub web base path')
  })
})

describe('runtime paths', () => {
  it('keeps root deployments unchanged', () => {
    setRuntimeConfig()

    expect(getAppBasePath()).toBe('')
    expect(getApiBaseUrl()).toBe('')
    expect(buildAppPath('/dashboard')).toBe('/dashboard')
    expect(toAppRelativePath('/dashboard?tab=skills#latest')).toBe('/dashboard?tab=skills#latest')
  })

  it('uses the application base as the same-origin API fallback', () => {
    setRuntimeConfig({ basePath: '/skillhub/' })

    expect(getAppBasePath()).toBe('/skillhub')
    expect(getApiBaseUrl()).toBe('/skillhub')
    expect(buildAppPath('/dashboard')).toBe('/skillhub/dashboard')
    expect(toAppRelativePath('/skillhub/dashboard?tab=skills#latest')).toBe('/dashboard?tab=skills#latest')
  })

  it('prefers an explicit API base URL', () => {
    setRuntimeConfig({
      basePath: '/skillhub',
      apiBaseUrl: 'https://api.example.com/gateway/',
    })

    expect(getApiBaseUrl()).toBe('https://api.example.com/gateway')
  })

  it('rejects paths outside the configured application base', () => {
    setRuntimeConfig({ basePath: '/skillhub' })

    expect(toAppRelativePath('/other/dashboard')).toBeUndefined()
    expect(toAppRelativePath('/skillhub-other/dashboard')).toBeUndefined()
  })
})

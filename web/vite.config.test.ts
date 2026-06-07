import { describe, expect, it } from 'vitest'
import config from './vite.config'

type ProxyTarget = {
  target?: string
}

describe('Vite dev proxy route ownership', () => {
  it('routes Python-owned health before the Java API fallback', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)

    expect(proxy['/api/v1/health']?.target).toBe('http://localhost:8081')
    expect(proxy['/api']?.target).toBe('http://localhost:8080')
    expect(keys.indexOf('/api/v1/health')).toBeLessThan(keys.indexOf('/api'))
  })

  it('keeps OAuth owned by Java', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>

    expect(proxy['/oauth2']?.target).toBe('http://localhost:8080')
  })

  it('routes ClawHub well-known discovery to Python', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)

    expect(proxy['/.well-known/clawhub.json']?.target).toBe('http://localhost:8081')
    expect(keys).toContain('/.well-known/clawhub.json')
    expect(keys.indexOf('/.well-known/clawhub.json')).toBeLessThan(keys.indexOf('/api'))
  })

  it('routes public labels aliases to Python before the Java API fallback', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)

    expect(proxy['/api/v1/labels']?.target).toBe('http://localhost:8081')
    expect(proxy['/api/web/labels']?.target).toBe('http://localhost:8081')
    expect(keys.indexOf('/api/v1/labels')).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf('/api/web/labels')).toBeLessThan(keys.indexOf('/api'))
  })

  it('routes skill labels aliases to Python without taking over all skill routes', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const v1SkillLabels = '^/api/v1/skills/[^/]+/[^/]+/labels$'
    const webSkillLabels = '^/api/web/skills/[^/]+/[^/]+/labels$'

    expect(proxy[v1SkillLabels]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillLabels]?.target).toBe('http://localhost:8081')
    expect(proxy['/api/v1/skills']?.target).toBeUndefined()
    expect(proxy['/api/web/skills']?.target).toBeUndefined()
    expect(keys.indexOf(v1SkillLabels)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillLabels)).toBeLessThan(keys.indexOf('/api'))
  })

  it('routes skill resolve aliases to Python without taking over all skill routes', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const v1SkillResolve = '^/api/v1/skills/[^/]+/[^/]+/resolve$'
    const webSkillResolve = '^/api/web/skills/[^/]+/[^/]+/resolve$'

    expect(proxy[v1SkillResolve]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillResolve]?.target).toBe('http://localhost:8081')
    expect(proxy['/api/v1/skills']?.target).toBeUndefined()
    expect(proxy['/api/web/skills']?.target).toBeUndefined()
    expect(keys.indexOf(v1SkillResolve)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillResolve)).toBeLessThan(keys.indexOf('/api'))
  })

  it('routes skill versions list aliases to Python without taking over all skill routes', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const v1SkillVersions = '^/api/v1/skills/[^/]+/[^/]+/versions$'
    const webSkillVersions = '^/api/web/skills/[^/]+/[^/]+/versions$'

    expect(proxy[v1SkillVersions]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillVersions]?.target).toBe('http://localhost:8081')
    expect(proxy['/api/v1/skills']?.target).toBeUndefined()
    expect(proxy['/api/web/skills']?.target).toBeUndefined()
    expect(keys.indexOf(v1SkillVersions)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillVersions)).toBeLessThan(keys.indexOf('/api'))
  })

  it('routes skill version detail aliases to Python without taking over file or compare routes', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const v1SkillVersionDetail = '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+$'
    const webSkillVersionDetail = '^/api/web/skills/[^/]+/[^/]+/versions/[^/]+$'

    expect(proxy[v1SkillVersionDetail]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillVersionDetail]?.target).toBe('http://localhost:8081')
    expect(proxy['^/api/v1/skills/[^/]+/[^/]+/versions/compare$']?.target).toBeUndefined()
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/compare$']?.target).toBeUndefined()
    expect(proxy['^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/file$']?.target).toBeUndefined()
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/file$']?.target).toBeUndefined()
    expect(proxy['^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/download$']?.target).toBeUndefined()
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/download$']?.target).toBeUndefined()
    expect(keys.indexOf(v1SkillVersionDetail)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillVersionDetail)).toBeLessThan(keys.indexOf('/api'))
  })

  it('routes skill files list aliases to Python without taking over file content or download routes', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const v1SkillVersionFiles = '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/files$'
    const webSkillVersionFiles = '^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/files$'
    const v1SkillTagFiles = '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/files$'
    const webSkillTagFiles = '^/api/web/skills/[^/]+/[^/]+/tags/[^/]+/files$'

    expect(proxy[v1SkillVersionFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillVersionFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[v1SkillTagFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillTagFiles]?.target).toBe('http://localhost:8081')

    // file and download should NOT route to Python
    expect(proxy['^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/file$']?.target).toBeUndefined()
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/file$']?.target).toBeUndefined()
    expect(proxy['^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/download$']?.target).toBeUndefined()
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/download$']?.target).toBeUndefined()

    expect(keys.indexOf(v1SkillVersionFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillVersionFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(v1SkillTagFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillTagFiles)).toBeLessThan(keys.indexOf('/api'))
  })
})

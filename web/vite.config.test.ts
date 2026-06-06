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
})

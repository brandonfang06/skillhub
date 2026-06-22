import { describe, expect, it } from 'vitest'
import config, { PYTHON_BACKEND_PROXY_PREFIXES } from './vite.config'

type ProxyTarget = {
  target?: string
}

function matchingProxyTarget(pathname: string): string | undefined {
  const proxy = config.server?.proxy as Record<string, ProxyTarget>
  for (const [key, value] of Object.entries(proxy)) {
    if (pathname.startsWith(key)) {
      return value.target
    }
  }

  return undefined
}

describe('Vite dev proxy route ownership', () => {
  it('uses a small Python-only proxy prefix set', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>

    expect(Object.keys(proxy)).toEqual([...PYTHON_BACKEND_PROXY_PREFIXES])
    expect(Object.values(proxy).map((value) => value.target)).toEqual(
      PYTHON_BACKEND_PROXY_PREFIXES.map(() => 'http://localhost:8081'),
    )
  })

  it('routes backend API traffic to the Python backend', () => {
    expect(matchingProxyTarget('/api/v1/health')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/cli/v1/skills/search?q=agent')).toBe('http://localhost:8081')
  })

  it('routes OAuth and well-known backend traffic to the Python backend', () => {
    expect(matchingProxyTarget('/oauth2/authorization/keycloak')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/login/oauth2/code/keycloak')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/.well-known/clawhub.json')).toBe('http://localhost:8081')
  })

  it('does not proxy frontend-owned routes', () => {
    expect(matchingProxyTarget('/')).toBeUndefined()
    expect(matchingProxyTarget('/search')).toBeUndefined()
    expect(matchingProxyTarget('/dashboard')).toBeUndefined()
  })

  it('removes Java and hybrid proxy targets', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>

    expect(Object.values(proxy).map((value) => value.target)).not.toContain('http://localhost:8080')
    expect('METHOD_AWARE_PROXY_RULES' in config).toBe(false)
  })
})

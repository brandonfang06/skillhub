import { describe, expect, it } from 'vitest'
import config, {
  type MethodAwareProxyRule,
  resolveMethodAwareProxyTarget,
} from './vite.config'

type ProxyTarget = {
  target?: string
}

function matchingProxyTarget(pathname: string): string | undefined {
  const proxy = config.server?.proxy as Record<string, ProxyTarget>
  for (const [key, value] of Object.entries(proxy)) {
    if (key.startsWith('^')) {
      if (new RegExp(key).test(pathname)) {
        return value.target
      }
      continue
    }

    if (pathname.startsWith(key)) {
      return value.target
    }
  }

  return undefined
}

function matchingDevProxyTarget(method: string, pathname: string): string | undefined {
  return resolveMethodAwareProxyTarget(method, pathname) ?? matchingProxyTarget(pathname)
}

describe('Vite dev proxy route ownership', () => {
  it('resolves method-aware GET-only proxy targets without taking over mutations', () => {
    const rules: MethodAwareProxyRule[] = [
      {
        methods: ['GET'],
        pattern: /^\/api\/v1\/skills\/[^/?]+(?:\?.*)?$/,
        target: 'http://localhost:8081',
      },
    ]

    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/demo', rules)).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/team-ai--demo?view=compat', rules)).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/v1/skills/demo', rules)).toBeUndefined()
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/skills/demo', rules)).toBeUndefined()
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/global/demo', rules)).toBeUndefined()
  })

  it('routes ClawHub skill detail GET to Python without taking over mutations', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills?page=0&limit=25')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/skills')).toBeUndefined()
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/demo')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/team-ai--demo?view=compat')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/v1/skills/demo')).toBeUndefined()
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/skills/demo')).toBeUndefined()

    expect(matchingDevProxyTarget('GET', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/skills/demo')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('DELETE', '/api/v1/skills/demo')).toBe('http://localhost:8080')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills/demo/undelete')).toBe('http://localhost:8080')
  })

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

  it('routes current user and auth catalog reads to Python while keeping auth setup writes on Java', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const authMe = '^/api/v1/auth/me(?:\\?.*)?$'
    const authCatalog = '^/api/v1/auth/(?:methods|providers)(?:\\?.*)?$'

    expect(proxy[authMe]?.target).toBe('http://localhost:8081')
    expect(keys.indexOf(authMe)).toBeLessThan(keys.indexOf('/api'))
    expect(proxy[authCatalog]?.target).toBe('http://localhost:8081')
    expect(keys.indexOf(authCatalog)).toBeLessThan(keys.indexOf('/api'))

    expect(matchingProxyTarget('/api/v1/auth/me')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/auth/me?fresh=true')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/auth/methods')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/auth/providers')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/auth/direct/login')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/api/v1/auth/session/bootstrap')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/oauth2/authorization/github')).toBe('http://localhost:8080')
  })

  it('routes whoami reads to Python while keeping auth writers on Java', () => {
    expect(matchingProxyTarget('/api/v1/whoami')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/cli/v1/auth/whoami')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/auth/direct/login')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/api/v1/auth/session/bootstrap')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/oauth2/authorization/github')).toBe('http://localhost:8080')
  })

  it('routes API token management to Python while keeping OAuth on Java', () => {
    expect(matchingProxyTarget('/api/v1/tokens')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/tokens?page=1&size=10')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/tokens/7')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/tokens/7/expiration')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/oauth2/authorization/github')).toBe('http://localhost:8080')
  })

  it('routes local auth core and password reset to Python while keeping direct/session/OAuth on Java', () => {
    expect(matchingProxyTarget('/api/v1/auth/local/password-reset/request')).toBe(
      'http://localhost:8081',
    )
    expect(matchingProxyTarget('/api/v1/auth/local/password-reset/confirm')).toBe(
      'http://localhost:8081',
    )
    expect(matchingProxyTarget('/api/v1/auth/local/login')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/auth/local/register')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/auth/local/change-password')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/auth/direct/login')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/api/v1/auth/session/bootstrap')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/oauth2/authorization/github')).toBe('http://localhost:8080')
  })

  it('routes skill report submit aliases to Python without changing nearby reads', () => {
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-ai/reported-skill/reports')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/skills/team-ai/reported-skill/reports')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/team-ai/reported-skill/reports')).toBeUndefined()
    expect(matchingDevProxyTarget('POST', '/api/v1/skills/team-ai/reported-skill/reports')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/skills/team-ai/reported-skill/reports')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('GET', '/api/v1/skills/team-ai/reported-skill')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('GET', '/api/web/skills/team-ai/reported-skill/download')).toBe(
      'http://localhost:8081',
    )
  })

  it('routes review lifecycle POST actions to Python without taking over other review routes', () => {
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/reviews/701/approve')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/reviews/701/approve')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/reviews/701/reject')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/reviews/701/reject')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/reviews/701/withdraw')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/reviews/701/withdraw')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/reviews')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/reviews')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/reviews?draft=true')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/reviews')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/reviews')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/reviews?status=PENDING')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/reviews/pending?namespaceId=20')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/reviews/my-submissions')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/reviews/701')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/reviews/701')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/reviews/701?include=basic')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/reviews/701/skill-detail')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/reviews/701/skill-detail')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/reviews/701/file?path=SKILL.md')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/reviews/701/file?path=SKILL.md')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/reviews/701/download')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/reviews/701/download')).toBe(
      'http://localhost:8081',
    )

    expect(matchingDevProxyTarget('POST', '/api/v1/reviews/701/approve')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/web/reviews/701/approve')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/reviews/701/reject')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/web/reviews/701/reject')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/reviews/701/withdraw')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/web/reviews/701/withdraw')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/reviews')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/web/reviews')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/reviews')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/reviews')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/reviews/pending?namespaceId=20')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('GET', '/api/web/reviews/my-submissions')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/reviews/701')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/reviews/701')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/reviews/701/skill-detail')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/reviews/701/skill-detail')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/reviews/701/file?path=SKILL.md')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/reviews/701/file?path=SKILL.md')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/reviews/701/download')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/reviews/701/download')).toBe('http://localhost:8081')
  })

  it('routes promotion read and write APIs to Python', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/promotions')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/promotions?status=APPROVED')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/promotions/pending')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/promotions/pending?page=1')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/promotions/301')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/promotions/301')).toBe(
      'http://localhost:8081',
    )

    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/promotions')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/promotions')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/promotions/301/approve')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/promotions/301/approve')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/promotions/301/reject')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/promotions/301/reject')).toBe(
      'http://localhost:8081',
    )

    expect(matchingDevProxyTarget('GET', '/api/v1/promotions')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/promotions/pending')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/promotions/301')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/promotions')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/web/promotions')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/promotions/301/reject')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/promotions/301/reject')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/v1/promotions/301/approve')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/promotions/301/approve')).toBe(
      'http://localhost:8081',
    )
  })

  it('routes skill archive and unarchive lifecycle actions to Python only', () => {
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/archive')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/skills/team-a/agent-helper/archive')).toBe(
      'http://localhost:8081',
    )
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/unarchive'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/web/skills/team-a/agent-helper/unarchive'),
    ).toBe('http://localhost:8081')

    expect(
      resolveMethodAwareProxyTarget('DELETE', '/api/v1/skills/team-a/agent-helper/versions/1.0.0'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/versions/1.0.0/rerelease'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/submit-review'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/web/skills/team-a/agent-helper/submit-review'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/confirm-publish'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/web/skills/team-a/agent-helper/confirm-publish'),
    ).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/skills/101/hide')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/skills/101/unhide')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/skills/versions/501/yank')).toBe(
      'http://localhost:8081',
    )

    expect(matchingDevProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/archive')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/skills/team-a/agent-helper/unarchive')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/v1/admin/skills/versions/501/yank')).toBe(
      'http://localhost:8081',
    )
  })

  it('routes skill star viewer-state actions to Python including unstar', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/101/star')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/skills/101/star')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/v1/skills/101/star')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/skills/101/star')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/web/skills/101/star')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/web/skills/101/star')).toBe('http://localhost:8081')

    expect(matchingDevProxyTarget('GET', '/api/v1/skills/101/star')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('DELETE', '/api/web/skills/101/star')).toBe('http://localhost:8081')
  })

  it('routes skill subscription viewer-state actions to Python including unsubscribe', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/101/subscription')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/skills/101/subscription')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/v1/skills/101/subscription')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/skills/101/subscription')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('PUT', '/api/web/skills/101/subscription')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/web/skills/101/subscription')).toBe(
      'http://localhost:8081',
    )

    expect(matchingDevProxyTarget('GET', '/api/v1/skills/101/subscription')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('DELETE', '/api/web/skills/101/subscription')).toBe('http://localhost:8081')
  })

  it('routes skill rating viewer-state actions to Python', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/skills/101/rating')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/skills/101/rating')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/skills/101/rating')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/web/skills/101/rating')).toBe('http://localhost:8081')

    expect(matchingDevProxyTarget('GET', '/api/v1/skills/101/rating')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('PUT', '/api/web/skills/101/rating')).toBe('http://localhost:8081')
  })

  it('routes my social lists to Python while my skills stays Java-owned', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/me/stars')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/me/stars')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/me/subscriptions')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/me/subscriptions')).toBe('http://localhost:8081')

    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/me/stars')).toBeUndefined()
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/me/skills')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/me/skills')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/me/skills')).toBeUndefined()

    expect(matchingDevProxyTarget('GET', '/api/v1/me/stars?page=0&size=12')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/me/subscriptions')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/me/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/me/skills?filter=HIDDEN')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/me/skills')).toBe('http://localhost:8080')
  })

  it('routes namespace read APIs to Python without taking over mutations', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/namespaces')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/namespaces?page=1')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/me/namespaces')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/me/namespaces')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/namespaces/team-a')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/namespaces/team-a?detail=true')).toBe(
      'http://localhost:8081',
    )

    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/namespaces')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/namespaces')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/web/namespaces/team-a')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/v1/namespaces/team-a')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/namespaces/team-a/freeze')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/namespaces/team-a/unfreeze')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/namespaces/team-a/archive')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/namespaces/team-a/restore')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/namespaces/team-a/members')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/namespaces/team-a/members?page=1')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/namespaces/team-a/member-candidates?search=ca')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/namespaces/team-a/member-candidates')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/namespaces/team-a/members')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/namespaces/team-a/members')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/v1/namespaces/team-a/members/user-1')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/web/namespaces/team-a/members/user-1')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/namespaces/team-a/members/user-1/role')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('PUT', '/api/web/namespaces/team-a/members/user-1/role')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/namespaces/team-a/members/batch')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/namespaces/team-a/members/batch')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/namespaces/team-a/transfer-ownership')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/namespaces/team-a/transfer-ownership')).toBe(
      'http://localhost:8081',
    )

    expect(matchingDevProxyTarget('GET', '/api/v1/namespaces')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/namespaces/team-a')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/namespaces')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('PUT', '/api/web/namespaces/team-a')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('DELETE', '/api/v1/namespaces/team-a')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/namespaces/team-a/freeze')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/namespaces/team-a/restore')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('GET', '/api/v1/namespaces/team-a/members')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('GET', '/api/web/namespaces/team-a/member-candidates?search=ca')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/v1/namespaces/team-a/members')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('PUT', '/api/web/namespaces/team-a/members/user-1/role')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('DELETE', '/api/web/namespaces/team-a/members/user-1')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/namespaces/team-a/members/batch')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/v1/namespaces/team-a/transfer-ownership')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/namespaces/team-a/transfer-ownership')).toBe(
      'http://localhost:8081',
    )
  })

  it('routes notification read-state APIs to Python while SSE and preferences stay Java-owned', () => {
    for (const prefix of ['/api/v1', '/api/web']) {
      expect(resolveMethodAwareProxyTarget('GET', `${prefix}/notifications`)).toBe(
        'http://localhost:8081',
      )
      expect(resolveMethodAwareProxyTarget('GET', `${prefix}/notifications?page=1&size=5`)).toBe(
        'http://localhost:8081',
      )
      expect(resolveMethodAwareProxyTarget('GET', `${prefix}/notifications/unread-count`)).toBe(
        'http://localhost:8081',
      )
      expect(resolveMethodAwareProxyTarget('PUT', `${prefix}/notifications/11/read`)).toBe(
        'http://localhost:8081',
      )
      expect(resolveMethodAwareProxyTarget('PUT', `${prefix}/notifications/read-all`)).toBe(
        'http://localhost:8081',
      )
      expect(resolveMethodAwareProxyTarget('DELETE', `${prefix}/notifications/11`)).toBe(
        'http://localhost:8081',
      )

      expect(resolveMethodAwareProxyTarget('GET', `${prefix}/notifications/sse`)).toBeUndefined()
      expect(resolveMethodAwareProxyTarget('GET', `${prefix}/notification-preferences`)).toBe(
        'http://localhost:8081',
      )
      expect(resolveMethodAwareProxyTarget('PUT', `${prefix}/notification-preferences`)).toBe(
        'http://localhost:8081',
      )

      expect(matchingDevProxyTarget('GET', `${prefix}/notifications`)).toBe('http://localhost:8081')
      expect(matchingDevProxyTarget('GET', `${prefix}/notifications/unread-count`)).toBe(
        'http://localhost:8081',
      )
      expect(matchingDevProxyTarget('PUT', `${prefix}/notifications/11/read`)).toBe(
        'http://localhost:8081',
      )
      expect(matchingDevProxyTarget('PUT', `${prefix}/notifications/read-all`)).toBe(
        'http://localhost:8081',
      )
      expect(matchingDevProxyTarget('DELETE', `${prefix}/notifications/11`)).toBe(
        'http://localhost:8081',
      )
      expect(matchingDevProxyTarget('GET', `${prefix}/notifications/sse`)).toBe('http://localhost:8080')
      expect(matchingDevProxyTarget('GET', `${prefix}/notification-preferences`)).toBe(
        'http://localhost:8081',
      )
      expect(matchingDevProxyTarget('PUT', `${prefix}/notification-preferences`)).toBe(
        'http://localhost:8081',
      )
    }
  })

  it('routes skill version delete lifecycle action to Python only', () => {
    expect(
      resolveMethodAwareProxyTarget('DELETE', '/api/v1/skills/team-a/agent-helper/versions/1.1.0'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('DELETE', '/api/web/skills/team-a/agent-helper/versions/1.1.0'),
    ).toBe('http://localhost:8081')

    expect(
      resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/versions/1.1.0/rerelease'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/versions/1.1.0/withdraw-review'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/web/skills/team-a/agent-helper/versions/1.1.0/withdraw-review'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/submit-review'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/web/skills/team-a/agent-helper/submit-review'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/confirm-publish'),
    ).toBe('http://localhost:8081')
    expect(
      resolveMethodAwareProxyTarget('POST', '/api/web/skills/team-a/agent-helper/confirm-publish'),
    ).toBe('http://localhost:8081')

    expect(matchingDevProxyTarget('DELETE', '/api/v1/skills/team-a/agent-helper/versions/1.1.0')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('DELETE', '/api/web/skills/team-a/agent-helper/versions/1.1.0')).toBe(
      'http://localhost:8081',
    )
    expect(
      matchingDevProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/versions/1.1.0/withdraw-review'),
    ).toBe('http://localhost:8081')
    expect(
      matchingDevProxyTarget('POST', '/api/web/skills/team-a/agent-helper/versions/1.1.0/withdraw-review'),
    ).toBe('http://localhost:8081')
    expect(
      matchingDevProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/versions/1.1.0/rerelease'),
    ).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/confirm-publish')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/skills/team-a/agent-helper/confirm-publish')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/v1/skills/team-a/agent-helper/submit-review')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/skills/team-a/agent-helper/submit-review')).toBe(
      'http://localhost:8081',
    )
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

  it('routes admin label definition APIs and skill label mutations to Python', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/labels')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/labels?type=RECOMMENDED')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/labels')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/admin/labels/featured')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/v1/admin/labels/featured')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/admin/labels/sort-order')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PATCH', '/api/v1/admin/labels/featured')).toBeUndefined()
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/admin/labels')).toBeUndefined()

    expect(matchingDevProxyTarget('GET', '/api/v1/admin/labels')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('PUT', '/api/v1/admin/labels/sort-order')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/skills/global/demo/labels/featured')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/web/skills/global/demo/labels/featured')).toBe(
      'http://localhost:8081',
    )

    expect(matchingDevProxyTarget('PUT', '/api/v1/skills/global/demo/labels/featured')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('DELETE', '/api/v1/skills/global/demo/labels/featured')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('PUT', '/api/web/skills/global/demo/labels/featured')).toBe('http://localhost:8081')
  })

  it('routes admin user management APIs and password reset to Python', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/users')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/users?page=0&size=20')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/admin/users/user-1/role')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('PUT', '/api/v1/admin/users/user-1/status')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/users/user-1/approve')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/users/user-1/disable')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/users/user-1/enable')).toBe('http://localhost:8081')
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/users/user-1/password-reset')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('DELETE', '/api/v1/admin/users/user-1')).toBeUndefined()

    expect(matchingDevProxyTarget('GET', '/api/v1/admin/users')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/admin/users/user-1/password-reset')).toBe('http://localhost:8081')
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

  it('routes public skill detail aliases to Python without taking over search or nested routes', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const v1SkillDetail = '^/api/v1/skills/[^/]+/(?!undelete(?:\\?.*)?$)[^/]+$'
    const webSkillDetail = '^/api/web/skills/[^/]+/[^/]+$'

    expect(proxy[v1SkillDetail]?.target).toBeUndefined()
    expect(proxy[webSkillDetail]?.target).toBeUndefined()

    expect(matchingDevProxyTarget('GET', '/api/v1/skills/global/demo')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/skills/global/demo')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills/global/demo')).toBe('http://localhost:8080')
    expect(matchingDevProxyTarget('POST', '/api/web/skills/global/demo')).toBe('http://localhost:8080')
    expect(matchingDevProxyTarget('GET', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/demo/undelete')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/labels')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/resolve')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/versions')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/download')).toBe('http://localhost:8081')
  })

  it('routes portal skill search and ClawHub v1 skills list to Python', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)

    const webSkillSearch = '^/api/web/skills(?:\\?.*)?$'

    expect(proxy[webSkillSearch]?.target).toBe('http://localhost:8081')
    expect(proxy['/api/v1/skills']?.target).toBeUndefined()
    expect(keys.indexOf(webSkillSearch)).toBeLessThan(keys.indexOf('/api'))

    expect(matchingProxyTarget('/api/web/skills')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills?q=agent')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/skills?page=0&limit=25')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/download')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/skills/global/demo')).toBe('http://localhost:8081')
  })

  it('routes root, legacy, and portal publish aliases to Python', () => {
    expect(matchingDevProxyTarget('POST', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/publish')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills/global/publish')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/web/skills/global/publish')).toBe('http://localhost:8081')

    expect(matchingDevProxyTarget('GET', '/api/v1/skills/global/demo')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/skills/global/demo')).toBe('http://localhost:8081')
  })

  it('routes ClawHub search to Python without taking over other ClawHub routes', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const clawHubSearch = '^/api/v1/search(?:\\?.*)?$'

    expect(proxy[clawHubSearch]?.target).toBe('http://localhost:8081')
    expect(keys.indexOf(clawHubSearch)).toBeLessThan(keys.indexOf('/api'))

    expect(matchingProxyTarget('/api/v1/search')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/search?q=agent')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/search/extra')).toBe('http://localhost:8080')
    expect(matchingDevProxyTarget('GET', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/download/demo')).toBe('http://localhost:8081')
  })

  it('routes ClawHub resolve to Python without taking over skills', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const clawHubResolveQuery = '^/api/v1/resolve(?:\\?.*)?$'
    const clawHubResolvePath = '^/api/v1/resolve/[^/]+(?:\\?.*)?$'

    expect(proxy[clawHubResolveQuery]?.target).toBe('http://localhost:8081')
    expect(proxy[clawHubResolvePath]?.target).toBe('http://localhost:8081')
    expect(keys.indexOf(clawHubResolveQuery)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(clawHubResolvePath)).toBeLessThan(keys.indexOf('/api'))

    expect(matchingProxyTarget('/api/v1/resolve?slug=demo')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/resolve/demo')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/resolve/team-ai--demo?version=1.0.0')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/resolve/team-ai/demo')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/api/v1/download/demo')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/v1/skills/demo')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('DELETE', '/api/v1/skills/demo')).toBe('http://localhost:8080')
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

  it('routes skill version detail and compare aliases to Python', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const v1SkillVersionDetail = '^/api/v1/skills/[^/]+/[^/]+/versions/(?!compare$)[^/]+$'
    const webSkillVersionDetail = '^/api/web/skills/[^/]+/[^/]+/versions/(?!compare$)[^/]+$'
    const v1SkillVersionCompare = '^/api/v1/skills/[^/]+/[^/]+/versions/compare$'
    const webSkillVersionCompare = '^/api/web/skills/[^/]+/[^/]+/versions/compare$'

    expect(proxy[v1SkillVersionDetail]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillVersionDetail]?.target).toBe('http://localhost:8081')
    expect(proxy[v1SkillVersionCompare]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillVersionCompare]?.target).toBe('http://localhost:8081')
    expect(keys.indexOf(v1SkillVersionCompare)).toBeLessThan(keys.indexOf(v1SkillVersionDetail))
    expect(keys.indexOf(webSkillVersionCompare)).toBeLessThan(keys.indexOf(webSkillVersionDetail))
    expect(keys.indexOf(v1SkillVersionDetail)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillVersionDetail)).toBeLessThan(keys.indexOf('/api'))

    expect(matchingProxyTarget('/api/v1/skills/global/demo/versions/1.2.0')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/versions/1.2.0')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/versions/compare')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/versions/compare')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/versions/1.2.0/file')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/versions/1.2.0/file')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/versions/1.2.0/download')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/versions/1.2.0/download')).toBe('http://localhost:8081')
  })

  it('routes skill files list aliases, v1 file content, and web downloads to Python', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const v1SkillVersionFiles = '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/files$'
    const webSkillVersionFiles = '^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/files$'
    const v1SkillTagFiles = '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/files$'
    const webSkillTagFiles = '^/api/web/skills/[^/]+/[^/]+/tags/[^/]+/files$'
    const v1SkillVersionFile = '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/file$'
    const v1SkillTagFile = '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/file$'

    expect(proxy[v1SkillVersionFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillVersionFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[v1SkillTagFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillTagFiles]?.target).toBe('http://localhost:8081')

    expect(proxy[v1SkillVersionFile]?.target).toBe('http://localhost:8081')
    expect(proxy[v1SkillTagFile]?.target).toBe('http://localhost:8081')

    // web file aliases do not exist in Java, but web download aliases share the Java portal mapping
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/file$']?.target).toBeUndefined()
    expect(proxy['^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/download$']?.target).toBe('http://localhost:8081')
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/download$']?.target).toBe('http://localhost:8081')

    expect(keys.indexOf(v1SkillVersionFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillVersionFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(v1SkillTagFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillTagFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(v1SkillVersionFile)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(v1SkillTagFile)).toBeLessThan(keys.indexOf('/api'))

    expect(matchingProxyTarget('/api/v1/skills/global/demo/versions/1.2.0/files')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/versions/1.2.0/files')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/tags/stable/files')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/tags/stable/files')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/versions/1.2.0/file')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/tags/stable/file')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/tags/stable/file')).toBe('http://localhost:8080')
    expect(matchingProxyTarget('/api/web/skills/global/demo/versions/1.2.0/download')).toBe('http://localhost:8081')
  })

  it('routes planned v1 and web download paths to Python while keeping mutations on Java', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const clawHubDownloadQuery = '^/api/v1/download(?:\\?.*)?$'
    const clawHubDownloadPath = '^/api/v1/download/[^/]+(?:\\?.*)?$'
    const v1LatestDownload = '^/api/v1/skills/[^/]+/[^/]+/download$'
    const v1VersionDownload = '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/download$'
    const v1TagDownload = '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/download$'
    const webLatestDownload = '^/api/web/skills/[^/]+/[^/]+/download$'
    const webVersionDownload = '^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/download$'
    const webTagDownload = '^/api/web/skills/[^/]+/[^/]+/tags/[^/]+/download$'

    expect(proxy[clawHubDownloadQuery]?.target).toBe('http://localhost:8081')
    expect(proxy[clawHubDownloadPath]?.target).toBe('http://localhost:8081')
    expect(proxy[v1LatestDownload]?.target).toBe('http://localhost:8081')
    expect(proxy[v1VersionDownload]?.target).toBe('http://localhost:8081')
    expect(proxy[v1TagDownload]?.target).toBe('http://localhost:8081')
    expect(proxy[webLatestDownload]?.target).toBe('http://localhost:8081')
    expect(proxy[webVersionDownload]?.target).toBe('http://localhost:8081')
    expect(proxy[webTagDownload]?.target).toBe('http://localhost:8081')

    expect(keys.indexOf(clawHubDownloadQuery)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(clawHubDownloadPath)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(v1LatestDownload)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(v1VersionDownload)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(v1TagDownload)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webLatestDownload)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webVersionDownload)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webTagDownload)).toBeLessThan(keys.indexOf('/api'))

    expect(matchingProxyTarget('/api/v1/download?slug=demo&version=latest')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/download/demo')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/download/team-ai--demo?version=1.0.0')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/download')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/versions/1.0.0/download')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/demo/tags/stable/download')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/download')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/versions/1.0.0/download')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/demo/tags/stable/download')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/skills')).toBe('http://localhost:8081')
  })

  it('routes CLI publish validate and write to Python', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const cliValidate = '^/api/cli/v1/skills/[^/]+/publish/validate$'
    const cliWrite = '^/api/cli/v1/skills/[^/]+/publish$'

    expect(proxy[cliValidate]?.target).toBe('http://localhost:8081')
    expect(proxy[cliWrite]?.target).toBe('http://localhost:8081')
    expect(keys.indexOf(cliValidate)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(cliWrite)).toBeLessThan(keys.indexOf('/api'))

    expect(matchingProxyTarget('/api/cli/v1/skills/global/publish/validate')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/cli/v1/skills/global/publish')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/v1/skills/global/publish')).toBe('http://localhost:8081')
    expect(matchingProxyTarget('/api/web/skills/global/publish')).toBe('http://localhost:8081')
  })

  it('routes governance workbench reads and notification mark-read to Python', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/governance/summary')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/governance/summary')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/governance/inbox?type=REVIEW')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/web/governance/activity?page=0&size=20')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/governance/notifications')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/governance/notifications/1/read')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/web/governance/notifications/1/read')).toBe(
      'http://localhost:8081',
    )

    expect(matchingDevProxyTarget('GET', '/api/v1/governance/summary')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('GET', '/api/web/governance/notifications')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/governance/notifications/1/read')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/web/governance/notifications/1/read')).toBe(
      'http://localhost:8081',
    )
  })

  it('routes admin audit log reads to Python', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/audit-logs')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/audit-logs?page=0&size=20')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/audit-logs')).toBeUndefined()
    expect(matchingDevProxyTarget('GET', '/api/v1/admin/audit-logs')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/admin/audit-logs')).toBe('http://localhost:8080')
  })

  it('routes admin review/report reads and mutations to Python', () => {
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/skill-reports')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/skill-reports?status=pending')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/skill-reports/1/resolve')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/skill-reports/1/dismiss')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('GET', '/api/v1/admin/skill-reports')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/admin/skill-reports/1/resolve')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/v1/admin/skill-reports/1/dismiss')).toBe(
      'http://localhost:8081',
    )

    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/profile-reviews')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('GET', '/api/v1/admin/profile-reviews?sortDirection=ASC')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/profile-reviews/1/approve')).toBe(
      'http://localhost:8081',
    )
    expect(resolveMethodAwareProxyTarget('POST', '/api/v1/admin/profile-reviews/1/reject')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('GET', '/api/v1/admin/profile-reviews')).toBe('http://localhost:8081')
    expect(matchingDevProxyTarget('POST', '/api/v1/admin/profile-reviews/1/approve')).toBe(
      'http://localhost:8081',
    )
    expect(matchingDevProxyTarget('POST', '/api/v1/admin/profile-reviews/1/reject')).toBe(
      'http://localhost:8081',
    )
  })
})

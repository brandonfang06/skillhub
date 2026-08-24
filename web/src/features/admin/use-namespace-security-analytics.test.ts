import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchJsonMock = vi.fn()
vi.mock('@/api/client', () => ({
  fetchJson: (url: string) => fetchJsonMock(url),
}))

import {
  buildNamespaceSecurityAnalyticsUrl,
  buildNamespaceSecuritySkillsUrl,
  getNamespaceSecurityAnalytics,
  getNamespaceSecuritySkills,
  useNamespaceSecurityAnalytics,
  useNamespaceSecuritySkills,
} from './use-namespace-security-analytics'

const params = {
  query: 'platform tools',
  severity: 'HIGH' as const,
  namespaceType: 'TEAM' as const,
  namespaceStatus: 'ARCHIVED' as const,
  skillStatus: 'ARCHIVED' as const,
  visibility: 'PRIVATE' as const,
  hidden: 'HIDDEN' as const,
  versionStatus: 'UPLOADED' as const,
  scannerType: 'custom' as const,
  sort: 'risk' as const,
  direction: 'desc' as const,
  page: 1,
  size: 50,
}

describe('namespace security analytics query feature', () => {
  beforeEach(() => {
    fetchJsonMock.mockReset()
    fetchJsonMock.mockResolvedValue({ items: [] })
  })

  it('serializes every aggregate inventory filter', () => {
    expect(buildNamespaceSecurityAnalyticsUrl(params)).toBe(
      '/api/v1/admin/namespace-analytics/security?query=platform+tools&severity=HIGH&namespaceType=TEAM&namespaceStatus=ARCHIVED&skillStatus=ARCHIVED&visibility=PRIVATE&hidden=HIDDEN&versionStatus=UPLOADED&scannerType=custom&sort=risk&direction=desc&page=1&size=50',
    )
  })

  it('serializes lazy skill drill-down without aggregate-only filters', () => {
    expect(buildNamespaceSecuritySkillsUrl(42, params)).toBe(
      '/api/v1/admin/namespace-analytics/security/namespaces/42/skills?query=platform+tools&severity=HIGH&skillStatus=ARCHIVED&visibility=PRIVATE&hidden=HIDDEN&versionStatus=UPLOADED&scannerType=custom&sort=risk&direction=desc&page=1&size=50',
    )
  })

  it('uses the shared base-aware fetch boundary', async () => {
    await getNamespaceSecurityAnalytics(params)
    await getNamespaceSecuritySkills(42, params)

    expect(fetchJsonMock).toHaveBeenNthCalledWith(1, buildNamespaceSecurityAnalyticsUrl(params))
    expect(fetchJsonMock).toHaveBeenNthCalledWith(2, buildNamespaceSecuritySkillsUrl(42, params))
  })

  it('exports aggregate and lazy TanStack query hooks', () => {
    expect(useNamespaceSecurityAnalytics).toBeTypeOf('function')
    expect(useNamespaceSecuritySkills).toBeTypeOf('function')
  })
})

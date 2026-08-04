import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchJsonMock = vi.fn()
vi.mock('@/api/client', () => ({
  fetchJson: (url: string) => fetchJsonMock(url),
}))

import {
  buildNamespaceAnalyticsUrl,
  getNamespaceAnalytics,
  useNamespaceAnalytics,
} from './use-namespace-analytics'

const params = {
  query: 'platform tools',
  namespaceType: 'TEAM' as const,
  namespaceStatus: 'ACTIVE' as const,
  startTime: '2026-07-05T00:00:00.000Z',
  endTime: '2026-08-04T00:00:00.000Z',
  source: 'cli' as const,
  sort: 'periodDownloads' as const,
  direction: 'desc' as const,
  page: 1,
  size: 50,
}

describe('namespace analytics query feature', () => {
  beforeEach(() => {
    fetchJsonMock.mockReset()
    fetchJsonMock.mockResolvedValue({ items: [] })
  })

  it('serializes the typed API query', () => {
    expect(buildNamespaceAnalyticsUrl(params)).toBe(
      '/api/v1/admin/namespace-analytics?query=platform+tools&namespaceType=TEAM&namespaceStatus=ACTIVE&startTime=2026-07-05T00%3A00%3A00.000Z&endTime=2026-08-04T00%3A00%3A00.000Z&source=cli&sort=periodDownloads&direction=desc&page=1&size=50',
    )
  })

  it('uses the shared base-aware fetch boundary', async () => {
    await getNamespaceAnalytics(params)

    expect(fetchJsonMock).toHaveBeenCalledWith(buildNamespaceAnalyticsUrl(params))
  })

  it('exports the TanStack query hook', () => {
    expect(useNamespaceAnalytics).toBeTypeOf('function')
  })
})

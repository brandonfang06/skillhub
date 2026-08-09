// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { NamespaceAnalyticsParams } from '@/api/types'
import {
  buildNamespaceAnalyticsCsvUrl,
  exportNamespaceAnalyticsCsv,
} from './export-namespace-analytics'

const params: NamespaceAnalyticsParams = {
  query: 'platform team',
  namespaceType: 'TEAM',
  namespaceStatus: 'ALL',
  startTime: '2026-07-05T00:00:00.000Z',
  endTime: '2026-08-04T00:00:00.000Z',
  source: 'cli',
  sort: 'skills',
  direction: 'asc',
  page: 3,
  size: 50,
}

describe('namespace analytics CSV export', () => {
  const createObjectURL = vi.fn(() => 'blob:namespace-analytics')
  const revokeObjectURL = vi.fn()
  const click = vi.fn()

  beforeEach(() => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = {}
    vi.stubGlobal('fetch', vi.fn())
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(click)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    delete window.__SKILLHUB_RUNTIME_CONFIG__
    createObjectURL.mockClear()
    revokeObjectURL.mockClear()
    click.mockClear()
  })

  it('builds a root export URL from all filters and sorting without pagination', () => {
    expect(buildNamespaceAnalyticsCsvUrl(params)).toBe(
      '/api/v1/admin/namespace-analytics.csv?query=platform+team&namespaceType=TEAM&namespaceStatus=ALL&startTime=2026-07-05T00%3A00%3A00.000Z&endTime=2026-08-04T00%3A00%3A00.000Z&source=cli&sort=skills&direction=asc',
    )
    expect(buildNamespaceAnalyticsCsvUrl(params)).not.toContain('page=')
    expect(buildNamespaceAnalyticsCsvUrl(params)).not.toContain('size=')
  })

  it('uses the configured application base path for same-origin export', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { basePath: '/skillhub' }

    expect(buildNamespaceAnalyticsCsvUrl(params)).toMatch(
      /^\/skillhub\/api\/v1\/admin\/namespace-analytics\.csv\?/,
    )
  })

  it('downloads the CSV and returns truncation metadata', async () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { basePath: '/skillhub' }
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValue(new Response('namespace_id\r\n1\r\n', {
      status: 200,
      headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename="portfolio.csv"',
        'X-SkillHub-Export-Truncated': 'true',
        'X-SkillHub-Export-Row-Limit': '10000',
      },
    }))

    const result = await exportNamespaceAnalyticsCsv(params)

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/skillhub\/api\/v1\/admin\/namespace-analytics\.csv\?/),
      expect.objectContaining({
        credentials: 'same-origin',
        headers: expect.objectContaining({ Accept: 'text/csv' }),
      }),
    )
    expect(result).toEqual({ truncated: true, rowLimit: 10_000 })
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:namespace-analytics')
    expect(document.querySelector('a[download]')).toBeNull()
  })

  it('uses the stable filename when content disposition is absent', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('namespace_id\r\n', { status: 200 }))
    const appendSpy = vi.spyOn(document.body, 'appendChild')

    await exportNamespaceAnalyticsCsv(params)

    const link = appendSpy.mock.calls[0][0] as HTMLAnchorElement
    expect(link.download).toBe('skillhub-namespace-analytics.csv')
  })

  it('rejects a failed response without creating a download', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(
      JSON.stringify({ detail: 'error.admin.superAdminRequired' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    ))

    await expect(exportNamespaceAnalyticsCsv(params)).rejects.toThrow('error.admin.superAdminRequired')
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(click).not.toHaveBeenCalled()
  })
})

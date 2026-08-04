import { describe, expect, it } from 'vitest'
import {
  parseNamespaceAnalyticsSearch,
  resolveAnalyticsPeriod,
} from './namespace-analytics-search'

describe('namespace analytics search state', () => {
  it('provides the recommended defaults', () => {
    expect(parseNamespaceAnalyticsSearch({})).toEqual({
      query: undefined,
      namespaceType: 'ALL',
      namespaceStatus: 'ACTIVE',
      period: '30d',
      startTime: undefined,
      endTime: undefined,
      source: undefined,
      sort: 'periodDownloads',
      direction: 'desc',
      page: 0,
      size: 20,
    })
  })

  it('normalizes invalid URL values without widening the contract', () => {
    expect(parseNamespaceAnalyticsSearch({
      query: ' platform ',
      namespaceType: 'PERSONAL',
      namespaceStatus: 'DELETED',
      period: 'forever',
      source: 'mobile',
      sort: 'owner',
      direction: 'sideways',
      page: '-3',
      size: '500',
    })).toEqual({
      query: 'platform',
      namespaceType: 'ALL',
      namespaceStatus: 'ACTIVE',
      period: '30d',
      startTime: undefined,
      endTime: undefined,
      source: undefined,
      sort: 'periodDownloads',
      direction: 'desc',
      page: 0,
      size: 20,
    })
  })

  it.each([
    ['7d', '2026-07-28T00:00:00.000Z'],
    ['30d', '2026-07-05T00:00:00.000Z'],
    ['90d', '2026-05-06T00:00:00.000Z'],
  ] as const)('resolves the %s preset against one stable now', (period, startTime) => {
    expect(resolveAnalyticsPeriod(
      parseNamespaceAnalyticsSearch({ period }),
      new Date('2026-08-04T00:00:00Z'),
    )).toEqual({
      startTime,
      endTime: '2026-08-04T00:00:00.000Z',
    })
  })

  it('preserves a valid custom inclusive range', () => {
    expect(resolveAnalyticsPeriod(
      parseNamespaceAnalyticsSearch({
        period: 'custom',
        startTime: '2026-07-01T08:00:00Z',
        endTime: '2026-07-31T18:00:00Z',
      }),
      new Date('2026-08-04T00:00:00Z'),
    )).toEqual({
      startTime: '2026-07-01T08:00:00.000Z',
      endTime: '2026-07-31T18:00:00.000Z',
    })
  })

  it.each([
    [{ period: 'custom', startTime: '2026-08-03T00:00:00Z', endTime: '2026-08-01T00:00:00Z' }],
    [{ period: 'custom', startTime: '2026-08-01T00:00:00Z' }],
  ])('normalizes an invalid custom range to the visible thirty-day preset', (rawSearch) => {
    const search = parseNamespaceAnalyticsSearch(rawSearch)

    expect(search).toMatchObject({
      period: '30d',
      startTime: undefined,
      endTime: undefined,
    })
    expect(resolveAnalyticsPeriod(search, new Date('2026-08-04T00:00:00Z'))).toEqual({
      startTime: '2026-07-05T00:00:00.000Z',
      endTime: '2026-08-04T00:00:00.000Z',
    })
  })
})

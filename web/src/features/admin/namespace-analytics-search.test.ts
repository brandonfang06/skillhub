import { describe, expect, it } from 'vitest'
import {
  parseNamespaceAnalyticsSearch,
  resolveAnalyticsPeriod,
} from './namespace-analytics-search'

describe('namespace analytics search state', () => {
  it('provides the recommended defaults', () => {
    expect(parseNamespaceAnalyticsSearch({})).toEqual({
      view: 'catalog',
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
      view: 'catalog',
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

  it('uses risk-first all-inventory defaults for the security view', () => {
    expect(parseNamespaceAnalyticsSearch({ view: 'security' })).toEqual({
      view: 'security',
      query: undefined,
      namespaceType: 'ALL',
      namespaceStatus: 'ALL',
      period: '30d',
      startTime: undefined,
      endTime: undefined,
      source: undefined,
      sort: 'periodDownloads',
      direction: 'desc',
      page: 0,
      size: 20,
      severity: 'ALL',
      skillStatus: 'ALL',
      visibility: 'ALL',
      hidden: 'ALL',
      versionStatus: 'ALL',
      scannerType: undefined,
      securitySort: 'risk',
      securityDirection: 'desc',
      securityPage: 0,
      securitySize: 20,
    })
  })

  it('normalizes security filter values without losing archived and private inventory', () => {
    expect(parseNamespaceAnalyticsSearch({
      view: 'security',
      namespaceStatus: 'ARCHIVED',
      severity: 'CRITICAL',
      skillStatus: 'ARCHIVED',
      visibility: 'PRIVATE',
      hidden: 'HIDDEN',
      versionStatus: 'UPLOADED',
      scannerType: 'custom',
      securitySort: 'findings',
      securityDirection: 'asc',
      securityPage: '2',
      securitySize: '50',
    })).toMatchObject({
      view: 'security',
      namespaceStatus: 'ARCHIVED',
      severity: 'CRITICAL',
      skillStatus: 'ARCHIVED',
      visibility: 'PRIVATE',
      hidden: 'HIDDEN',
      versionStatus: 'UPLOADED',
      scannerType: 'custom',
      securitySort: 'findings',
      securityDirection: 'asc',
      securityPage: 2,
      securitySize: 50,
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

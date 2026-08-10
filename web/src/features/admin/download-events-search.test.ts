import { describe, expect, it } from 'vitest'
import { parseDownloadEventsSearch } from './download-events-search'

describe('download events route search', () => {
  it('accepts the analytics drill-down filters', () => {
    expect(parseDownloadEventsSearch({
      namespace: ' platform ',
      userQuery: ' Brandon ',
      userId: ' legacy-user ',
      source: 'cli',
      startTime: '2026-07-05T00:00:00Z',
      endTime: '2026-08-04T00:00:00Z',
    })).toEqual({
      namespace: 'platform',
      slug: undefined,
      version: undefined,
      userQuery: 'Brandon',
      userId: 'legacy-user',
      source: 'cli',
      startTime: '2026-07-05T00:00:00Z',
      endTime: '2026-08-04T00:00:00Z',
    })
  })

  it('drops unsupported source and date values at the route boundary', () => {
    expect(parseDownloadEventsSearch({
      source: 'mobile',
      startTime: 'not-a-date',
      endTime: 42,
    })).toEqual({
      namespace: undefined,
      slug: undefined,
      version: undefined,
      userQuery: undefined,
      userId: undefined,
      source: undefined,
      startTime: undefined,
      endTime: undefined,
    })
  })
})

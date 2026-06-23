import { describe, expect, it } from 'vitest'
import { getAuthQueryOptions } from './use-auth'

describe('shared getAuthQueryOptions', () => {
  it('keeps auth state fresh so shared hooks can scope session-sensitive queries', () => {
    const options = getAuthQueryOptions(true)

    expect(options.queryKey).toEqual(['auth', 'me'])
    expect(options.staleTime).toBe(0)
    expect(options.refetchOnWindowFocus).toBe(true)
    expect(options.refetchOnReconnect).toBe(true)
    expect(options.refetchInterval).toBe(60_000)
    expect(options.enabled).toBe(true)
  })
})

import { describe, expect, it } from 'vitest'
import { getAuthMethodsQueryOptions, useAuthMethods } from './use-auth-methods'

describe('getAuthMethodsQueryOptions', () => {
  it('contains an expected anonymous failure within the login page', () => {
    const options = getAuthMethodsQueryOptions('/dashboard')

    expect(options.queryKey).toEqual(['auth', 'methods', '/dashboard'])
    expect(options.retry).toBe(false)
    expect(options.meta).toEqual({ skipGlobalErrorHandler: true })
    expect(options.queryFn).toBeTypeOf('function')
  })
})

describe('useAuthMethods', () => {
  it('exports useAuthMethods hook', () => {
    expect(useAuthMethods).toBeTypeOf('function')
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  auth: { user: null as { userId: string } | null, isLoading: false },
  listNamespaces: vi.fn(),
  useQuery: vi.fn(),
}))

vi.mock('@tanstack/react-query', () => ({
  keepPreviousData: Symbol('keepPreviousData'),
  useQuery: (options: unknown) => mocks.useQuery(options),
}))

vi.mock('@/api/client', () => ({
  searchApi: { listNamespaces: (...args: unknown[]) => mocks.listNamespaces(...args) },
}))

vi.mock('@/features/auth/use-auth', () => ({ useAuth: () => mocks.auth }))

import { useSearchableNamespaces } from './use-searchable-namespaces'

describe('useSearchableNamespaces', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.auth.user = null
    mocks.auth.isLoading = false
    mocks.useQuery.mockImplementation((options: unknown) => options)
    mocks.listNamespaces.mockResolvedValue([])
  })

  it('uses an anonymous cache key and sends the normalized server query', async () => {
    useSearchableNamespaces('  AI Platform  ')
    const options = mocks.useQuery.mock.calls[0]?.[0] as {
      queryKey: unknown
      queryFn: () => Promise<unknown>
      enabled: boolean
    }

    expect(options.queryKey).toEqual(['search', 'namespaces', 'anonymous', 'AI Platform'])
    expect(options.enabled).toBe(true)
    await options.queryFn()
    expect(mocks.listNamespaces).toHaveBeenCalledWith({ q: 'AI Platform', limit: 20 })
  })

  it('partitions authenticated cache data and waits for auth resolution', () => {
    mocks.auth.user = { userId: 'user-a' }
    mocks.auth.isLoading = true

    useSearchableNamespaces('', true)
    const options = mocks.useQuery.mock.calls[0]?.[0] as { queryKey: unknown; enabled: boolean }

    expect(options.queryKey).toEqual(['search', 'namespaces', 'user-a', ''])
    expect(options.enabled).toBe(false)
  })
})

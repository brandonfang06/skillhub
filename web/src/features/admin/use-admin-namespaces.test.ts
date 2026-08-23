import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchJsonMock = vi.fn()
const invalidateQueries = vi.fn()
let mutationOptions: Record<string, unknown> | undefined

vi.mock('@/api/client', () => ({
  fetchJson: (...args: unknown[]) => fetchJsonMock(...args),
  getCsrfHeaders: (headers?: HeadersInit) => ({ ...headers, 'X-XSRF-TOKEN': 'csrf' }),
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: (options: unknown) => options,
  useMutation: (options: Record<string, unknown>) => {
    mutationOptions = options
    return options
  },
  useQueryClient: () => ({ invalidateQueries }),
}))

import {
  addAdminNamespaceMember,
  archiveAdminNamespace,
  buildAdminNamespacesUrl,
  getAdminNamespaceCandidates,
  getAdminNamespaceMembers,
  removeAdminNamespaceMember,
  transferAdminNamespaceOwnership,
  updateAdminNamespaceMemberRole,
  useAddAdminNamespaceMember,
  useFreezeAdminNamespace,
} from './use-admin-namespaces'

describe('admin namespace query and mutation feature', () => {
  beforeEach(() => {
    fetchJsonMock.mockReset()
    fetchJsonMock.mockResolvedValue({})
    invalidateQueries.mockReset()
    mutationOptions = undefined
  })

  it('serializes keyword, lifecycle, type and pagination filters', () => {
    expect(buildAdminNamespacesUrl({
      keyword: 'platform tools',
      status: 'FROZEN',
      type: 'TEAM',
      page: 2,
      size: 20,
    })).toBe('/api/v1/admin/namespaces?keyword=platform+tools&status=FROZEN&type=TEAM&page=2&size=20')
  })

  it('uses base-aware shared fetch and CSRF for member mutations', async () => {
    await addAdminNamespaceMember({ slug: 'platform tools', userId: 'u/1', role: 'ADMIN' })
    await updateAdminNamespaceMemberRole({ slug: 'platform tools', userId: 'u/1', role: 'MEMBER' })
    await removeAdminNamespaceMember({ slug: 'platform tools', userId: 'u/1' })

    expect(fetchJsonMock).toHaveBeenNthCalledWith(1, '/api/v1/admin/namespaces/platform%20tools/members', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ userId: 'u/1', role: 'ADMIN' }),
      headers: expect.objectContaining({ 'X-XSRF-TOKEN': 'csrf' }),
    }))
    expect(fetchJsonMock).toHaveBeenNthCalledWith(2, '/api/v1/admin/namespaces/platform%20tools/members/u%2F1/role', expect.objectContaining({ method: 'PUT' }))
    expect(fetchJsonMock).toHaveBeenNthCalledWith(3, '/api/v1/admin/namespaces/platform%20tools/members/u%2F1', expect.objectContaining({ method: 'DELETE' }))
  })

  it('serializes candidate search and ownership/lifecycle requests', async () => {
    await getAdminNamespaceCandidates('team-a', 'Jane Doe', 20)
    await transferAdminNamespaceOwnership({ slug: 'team-a', newOwnerId: 'jane' })
    await archiveAdminNamespace({ slug: 'team-a', reason: 'retired' })

    expect(fetchJsonMock).toHaveBeenNthCalledWith(1, '/api/v1/admin/namespaces/team-a/member-candidates?search=Jane+Doe&size=20')
    expect(fetchJsonMock).toHaveBeenNthCalledWith(2, '/api/v1/admin/namespaces/team-a/transfer-ownership', expect.objectContaining({
      body: JSON.stringify({ newOwnerId: 'jane' }),
    }))
    expect(fetchJsonMock).toHaveBeenNthCalledWith(3, '/api/v1/admin/namespaces/team-a/archive', expect.objectContaining({
      body: JSON.stringify({ reason: 'retired' }),
    }))
  })

  it('loads any requested member page instead of truncating at the first 100', async () => {
    await getAdminNamespaceMembers('team-a', 1, 50)

    expect(fetchJsonMock).toHaveBeenCalledWith(
      '/api/v1/admin/namespaces/team-a/members?page=1&size=50',
    )
  })

  it('invalidates admin and ordinary namespace cache scopes after mutation success', async () => {
    useAddAdminNamespaceMember()
    expect(mutationOptions).toBeDefined()
    await (mutationOptions?.onSuccess as (data: unknown, variables: { slug: string }) => Promise<void>)(
      {},
      { slug: 'team-a' },
    )

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['admin', 'namespaces'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['admin', 'namespaces', 'team-a'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['admin', 'namespaces', 'team-a', 'members'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['admin', 'namespaces', 'team-a', 'member-candidates'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['namespaces', 'my'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['namespaces', 'team-a'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['namespaces', 'team-a', 'members'] })
  })

  it('also invalidates namespace analytics after a lifecycle mutation', async () => {
    useFreezeAdminNamespace()
    await (mutationOptions?.onSuccess as (data: unknown, variables: { slug: string }) => Promise<void>)(
      {},
      { slug: 'team-a' },
    )

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['admin', 'namespace-analytics'] })
  })
})

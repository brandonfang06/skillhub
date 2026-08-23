import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson, getCsrfHeaders } from '@/api/client'
import type { components } from '@/api/generated/admin-namespaces-schema'

export type AdminNamespace = components['schemas']['AdminNamespaceSummary']
export type AdminNamespaceList = components['schemas']['AdminNamespaceListData']
export type AdminNamespaceMember = components['schemas']['AdminNamespaceMember']
export type AdminNamespaceMemberPage = components['schemas']['AdminNamespaceMemberPage']
export type AdminNamespaceCandidate = components['schemas']['AdminNamespaceCandidate']
export type AdminNamespaceRole = components['schemas']['AdminNamespaceMemberRequest']['role']
export type AdminNamespaceStatus = AdminNamespace['status']
export type AdminNamespaceType = AdminNamespace['type']

export interface AdminNamespaceListParams {
  keyword?: string
  status?: AdminNamespaceStatus
  type?: AdminNamespaceType
  page?: number
  size?: number
}

type MemberInput = { slug: string; userId: string; role: AdminNamespaceRole }
type MemberTarget = { slug: string; userId: string }
type OwnershipInput = { slug: string; newOwnerId: string }
type LifecycleInput = { slug: string; reason?: string }

function jsonMutation(method: 'POST' | 'PUT', body?: unknown): RequestInit {
  return {
    method,
    headers: getCsrfHeaders({ 'Content-Type': 'application/json' }),
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }
}

export function buildAdminNamespacesUrl(params: AdminNamespaceListParams): string {
  const search = new URLSearchParams()
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.status) search.set('status', params.status)
  if (params.type) search.set('type', params.type)
  search.set('page', String(params.page ?? 0))
  search.set('size', String(params.size ?? 20))
  return `/api/v1/admin/namespaces?${search}`
}

export function getAdminNamespaces(params: AdminNamespaceListParams): Promise<AdminNamespaceList> {
  return fetchJson<AdminNamespaceList>(buildAdminNamespacesUrl(params))
}

export function getAdminNamespace(slug: string): Promise<AdminNamespace> {
  return fetchJson<AdminNamespace>(`/api/v1/admin/namespaces/${encodeURIComponent(slug)}`)
}

export function getAdminNamespaceMembers(
  slug: string,
  page = 0,
  size = 100,
): Promise<AdminNamespaceMemberPage> {
  return fetchJson<AdminNamespaceMemberPage>(
    `/api/v1/admin/namespaces/${encodeURIComponent(slug)}/members?page=${page}&size=${size}`,
  )
}

export function getAdminNamespaceCandidates(
  slug: string,
  searchTerm: string,
  size = 20,
): Promise<AdminNamespaceCandidate[]> {
  const search = new URLSearchParams({ search: searchTerm, size: String(size) })
  return fetchJson<AdminNamespaceCandidate[]>(
    `/api/v1/admin/namespaces/${encodeURIComponent(slug)}/member-candidates?${search}`,
  )
}

export function addAdminNamespaceMember(input: MemberInput): Promise<AdminNamespaceMember> {
  return fetchJson(
    `/api/v1/admin/namespaces/${encodeURIComponent(input.slug)}/members`,
    jsonMutation('POST', { userId: input.userId, role: input.role }),
  )
}

export function batchAddAdminNamespaceMembers(
  slug: string,
  members: Array<{ userId: string; role: AdminNamespaceRole }>,
): Promise<components['schemas']['AdminNamespaceBatchMemberData']> {
  return fetchJson(
    `/api/v1/admin/namespaces/${encodeURIComponent(slug)}/members/batch`,
    jsonMutation('POST', { members }),
  )
}

export function updateAdminNamespaceMemberRole(input: MemberInput): Promise<AdminNamespaceMember> {
  return fetchJson(
    `/api/v1/admin/namespaces/${encodeURIComponent(input.slug)}/members/${encodeURIComponent(input.userId)}/role`,
    jsonMutation('PUT', { role: input.role }),
  )
}

export function removeAdminNamespaceMember(input: MemberTarget): Promise<{ message: string }> {
  return fetchJson(
    `/api/v1/admin/namespaces/${encodeURIComponent(input.slug)}/members/${encodeURIComponent(input.userId)}`,
    { method: 'DELETE', headers: getCsrfHeaders() },
  )
}

export function transferAdminNamespaceOwnership(input: OwnershipInput): Promise<{ message: string }> {
  return fetchJson(
    `/api/v1/admin/namespaces/${encodeURIComponent(input.slug)}/transfer-ownership`,
    jsonMutation('POST', { newOwnerId: input.newOwnerId }),
  )
}

function transitionAdminNamespace(action: string, input: LifecycleInput): Promise<AdminNamespace> {
  const body = action === 'freeze' || action === 'archive' ? { reason: input.reason || null } : undefined
  return fetchJson(
    `/api/v1/admin/namespaces/${encodeURIComponent(input.slug)}/${action}`,
    jsonMutation('POST', body),
  )
}

export const freezeAdminNamespace = (input: LifecycleInput) => transitionAdminNamespace('freeze', input)
export const unfreezeAdminNamespace = (input: LifecycleInput) => transitionAdminNamespace('unfreeze', input)
export const archiveAdminNamespace = (input: LifecycleInput) => transitionAdminNamespace('archive', input)
export const restoreAdminNamespace = (input: LifecycleInput) => transitionAdminNamespace('restore', input)

export function useAdminNamespaces(params: AdminNamespaceListParams) {
  return useQuery({
    queryKey: ['admin', 'namespaces', 'list', params],
    queryFn: () => getAdminNamespaces(params),
  })
}

export function useAdminNamespace(slug: string | null) {
  return useQuery({
    queryKey: ['admin', 'namespaces', slug],
    queryFn: () => getAdminNamespace(slug!),
    enabled: Boolean(slug),
  })
}

export function useAdminNamespaceMembers(slug: string | null, page = 0, size = 20) {
  return useQuery({
    queryKey: ['admin', 'namespaces', slug, 'members', { page, size }],
    queryFn: () => getAdminNamespaceMembers(slug!, page, size),
    enabled: Boolean(slug),
  })
}

export function useAdminNamespaceCandidates(slug: string | null, search: string) {
  return useQuery({
    queryKey: ['admin', 'namespaces', slug, 'member-candidates', search],
    queryFn: () => getAdminNamespaceCandidates(slug!, search),
    enabled: Boolean(slug) && search.trim().length >= 2,
  })
}

function useAdminNamespaceMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<unknown>,
  getSlug: (variables: TVariables) => string,
  options: { invalidateAnalytics?: boolean } = {},
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: async (_data, variables) => {
      const slug = getSlug(variables)
      const invalidations = [
        queryClient.invalidateQueries({ queryKey: ['admin', 'namespaces'] }),
        queryClient.invalidateQueries({ queryKey: ['admin', 'namespaces', slug] }),
        queryClient.invalidateQueries({ queryKey: ['admin', 'namespaces', slug, 'members'] }),
        queryClient.invalidateQueries({ queryKey: ['admin', 'namespaces', slug, 'member-candidates'] }),
        queryClient.invalidateQueries({ queryKey: ['namespaces', 'my'] }),
        queryClient.invalidateQueries({ queryKey: ['namespaces', slug] }),
        queryClient.invalidateQueries({ queryKey: ['namespaces', slug, 'members'] }),
      ]
      if (options.invalidateAnalytics) {
        invalidations.push(
          queryClient.invalidateQueries({ queryKey: ['admin', 'namespace-analytics'] }),
        )
      }
      await Promise.all(invalidations)
    },
  })
}

export const useAddAdminNamespaceMember = () =>
  useAdminNamespaceMutation(addAdminNamespaceMember, (input) => input.slug)
export const useUpdateAdminNamespaceMemberRole = () =>
  useAdminNamespaceMutation(updateAdminNamespaceMemberRole, (input) => input.slug)
export const useRemoveAdminNamespaceMember = () =>
  useAdminNamespaceMutation(removeAdminNamespaceMember, (input) => input.slug)
export const useTransferAdminNamespaceOwnership = () =>
  useAdminNamespaceMutation(transferAdminNamespaceOwnership, (input) => input.slug)
export const useFreezeAdminNamespace = () =>
  useAdminNamespaceMutation(freezeAdminNamespace, (input) => input.slug, { invalidateAnalytics: true })
export const useUnfreezeAdminNamespace = () =>
  useAdminNamespaceMutation(unfreezeAdminNamespace, (input) => input.slug, { invalidateAnalytics: true })
export const useArchiveAdminNamespace = () =>
  useAdminNamespaceMutation(archiveAdminNamespace, (input) => input.slug, { invalidateAnalytics: true })
export const useRestoreAdminNamespace = () =>
  useAdminNamespaceMutation(restoreAdminNamespace, (input) => input.slug, { invalidateAnalytics: true })

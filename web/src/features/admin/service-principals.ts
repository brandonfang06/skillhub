import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson, getCsrfHeaders } from '@/api/client'
import type { components } from '@/api/generated/service-principals-schema'
import { getApiBaseUrl } from '@/shared/lib/runtime-config'

export type ServicePrincipalStatus = 'ACTIVE' | 'DISABLED'

export type ServicePrincipal = {
  id: string
  code: string
  displayName: string
  status: ServicePrincipalStatus
  activeTokenCount: number
  nearestTokenExpiry: string | null
  lastUsedAt: string | null
  createdAt: string
  updatedAt: string
}

export type ServiceToken = {
  id: number
  servicePrincipalId: string
  name: string
  tokenPrefix: string
  scopes: string[]
  createdAt: string
  expiresAt: string | null
  lastUsedAt: string | null
  revokedAt: string | null
}

export type ServiceTokenSecret = ServiceToken & { token: string }
type CreatePrincipalRequest = components['schemas']['CreateServicePrincipalRequest']
type UpdatePrincipalRequest = components['schemas']['UpdateServicePrincipalRequest']
type CreateTokenRequest = components['schemas']['CreateServiceTokenRequest']
type RotateTokenRequest = components['schemas']['RotateServiceTokenRequest']

type PrincipalList = { items: ServicePrincipal[]; total: number; page: number; size: number }
type TokenList = { items: ServiceToken[] }

const principalKey = ['admin', 'service-principals'] as const

export function servicePrincipalsUrl(): string {
  return '/api/v1/admin/service-principals?page=0&size=100'
}

export function serviceTokensUrl(id: string): string {
  return `/api/v1/admin/service-principals/${encodeURIComponent(id)}/tokens`
}

async function mutation<T>(url: string, method: string, body?: unknown): Promise<T> {
  const headers = new Headers(await getCsrfHeaders())
  headers.set('Content-Type', 'application/json')
  return fetchJson<T>(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export function useServicePrincipals() {
  return useQuery({
    queryKey: principalKey,
    queryFn: () => fetchJson<PrincipalList>(servicePrincipalsUrl()),
  })
}

export function useServiceTokens(servicePrincipalId: string | null) {
  return useQuery({
    queryKey: [...principalKey, servicePrincipalId, 'tokens'],
    queryFn: () => fetchJson<TokenList>(`${serviceTokensUrl(servicePrincipalId ?? '')}?includeRevoked=true`),
    enabled: Boolean(servicePrincipalId),
  })
}

export function useServicePrincipalMutations() {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: principalKey })
  return {
    createPrincipal: useMutation({
      mutationFn: (body: CreatePrincipalRequest) => mutation<ServicePrincipal>('/api/v1/admin/service-principals', 'POST', body),
      onSuccess: refresh,
    }),
    updatePrincipal: useMutation({
      mutationFn: ({ id, ...body }: UpdatePrincipalRequest & { id: string }) => mutation<ServicePrincipal>(`/api/v1/admin/service-principals/${id}`, 'PATCH', body),
      onSuccess: refresh,
    }),
    createToken: useMutation({
      mutationFn: ({ id, ...body }: CreateTokenRequest & { id: string }) => mutation<ServiceTokenSecret>(`/api/v1/admin/service-principals/${id}/tokens`, 'POST', body),
      onSuccess: refresh,
    }),
    rotateToken: useMutation({
      mutationFn: ({ id, tokenId, expiresAt }: RotateTokenRequest & { id: string; tokenId: number }) => mutation<ServiceTokenSecret>(`/api/v1/admin/service-principals/${id}/tokens/${tokenId}/rotate`, 'POST', { expiresAt }),
      onSuccess: refresh,
    }),
    revokeToken: useMutation({
      mutationFn: async ({ id, tokenId }: { id: string; tokenId: number }) => {
        const response = await fetch(`${getApiBaseUrl()}/api/v1/admin/service-principals/${id}/tokens/${tokenId}`, {
          method: 'DELETE',
          headers: await getCsrfHeaders(),
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
      },
      onSuccess: refresh,
    }),
  }
}

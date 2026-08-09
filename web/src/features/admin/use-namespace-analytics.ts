import { useQuery } from '@tanstack/react-query'
import { fetchJson } from '@/api/client'
import type { NamespaceAnalyticsData, NamespaceAnalyticsParams } from '@/api/types'

export function buildNamespaceAnalyticsSearchParams(
  params: NamespaceAnalyticsParams,
  options: { includePagination: boolean },
): URLSearchParams {
  const searchParams = new URLSearchParams()
  if (params.query) searchParams.set('query', params.query)
  if (params.namespaceType) searchParams.set('namespaceType', params.namespaceType)
  if (params.namespaceStatus) searchParams.set('namespaceStatus', params.namespaceStatus)
  if (params.startTime) searchParams.set('startTime', params.startTime)
  if (params.endTime) searchParams.set('endTime', params.endTime)
  if (params.source) searchParams.set('source', params.source)
  if (params.sort) searchParams.set('sort', params.sort)
  if (params.direction) searchParams.set('direction', params.direction)
  if (options.includePagination) {
    searchParams.set('page', String(params.page ?? 0))
    searchParams.set('size', String(params.size ?? 20))
  }
  return searchParams
}

export function buildNamespaceAnalyticsUrl(params: NamespaceAnalyticsParams): string {
  const searchParams = buildNamespaceAnalyticsSearchParams(params, { includePagination: true })
  return `/api/v1/admin/namespace-analytics?${searchParams.toString()}`
}

export async function getNamespaceAnalytics(params: NamespaceAnalyticsParams): Promise<NamespaceAnalyticsData> {
  return fetchJson<NamespaceAnalyticsData>(buildNamespaceAnalyticsUrl(params))
}

export function useNamespaceAnalytics(params: NamespaceAnalyticsParams) {
  return useQuery({
    queryKey: ['admin', 'namespace-analytics', params],
    queryFn: () => getNamespaceAnalytics(params),
  })
}

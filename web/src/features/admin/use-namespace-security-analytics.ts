import { useQuery } from '@tanstack/react-query'
import { fetchJson } from '@/api/client'
import type {
  NamespaceSecurityAnalyticsData,
  NamespaceSecurityAnalyticsParams,
  NamespaceSecuritySkillsData,
  NamespaceSecuritySkillsParams,
} from '@/api/types'

type SecurityFilters = {
  query?: string | null
  severity?: string
  skillStatus?: string
  visibility?: string
  hidden?: string
  versionStatus?: string
  scannerType?: string | null
  sort?: string
  direction?: string
  page?: number
  size?: number
}

function buildSecuritySearchParams(params: SecurityFilters): URLSearchParams {
  const searchParams = new URLSearchParams()
  if (params.query) searchParams.set('query', params.query)
  if (params.severity) searchParams.set('severity', params.severity)
  if (params.skillStatus) searchParams.set('skillStatus', params.skillStatus)
  if (params.visibility) searchParams.set('visibility', params.visibility)
  if (params.hidden) searchParams.set('hidden', params.hidden)
  if (params.versionStatus) searchParams.set('versionStatus', params.versionStatus)
  if (params.scannerType) searchParams.set('scannerType', params.scannerType)
  if (params.sort) searchParams.set('sort', params.sort)
  if (params.direction) searchParams.set('direction', params.direction)
  searchParams.set('page', String(params.page ?? 0))
  searchParams.set('size', String(params.size ?? 20))
  return searchParams
}

export function buildNamespaceSecurityAnalyticsUrl(params: NamespaceSecurityAnalyticsParams): string {
  const searchParams = buildSecuritySearchParams(params)
  if (params.namespaceType) {
    searchParams.set('namespaceType', params.namespaceType)
  }
  if (params.namespaceStatus) {
    searchParams.set('namespaceStatus', params.namespaceStatus)
  }

  const ordered = new URLSearchParams()
  for (const key of ['query', 'severity']) {
    const value = searchParams.get(key)
    if (value) ordered.set(key, value)
  }
  if (params.namespaceType) ordered.set('namespaceType', params.namespaceType)
  if (params.namespaceStatus) ordered.set('namespaceStatus', params.namespaceStatus)
  for (const key of ['skillStatus', 'visibility', 'hidden', 'versionStatus', 'scannerType', 'sort', 'direction', 'page', 'size']) {
    const value = searchParams.get(key)
    if (value !== null) ordered.set(key, value)
  }
  return `/api/v1/admin/namespace-analytics/security?${ordered.toString()}`
}

export function buildNamespaceSecuritySkillsUrl(
  namespaceId: number,
  params: NamespaceSecuritySkillsParams,
): string {
  return `/api/v1/admin/namespace-analytics/security/namespaces/${namespaceId}/skills?${buildSecuritySearchParams(params).toString()}`
}

export async function getNamespaceSecurityAnalytics(
  params: NamespaceSecurityAnalyticsParams,
): Promise<NamespaceSecurityAnalyticsData> {
  return fetchJson<NamespaceSecurityAnalyticsData>(buildNamespaceSecurityAnalyticsUrl(params))
}

export async function getNamespaceSecuritySkills(
  namespaceId: number,
  params: NamespaceSecuritySkillsParams,
): Promise<NamespaceSecuritySkillsData> {
  return fetchJson<NamespaceSecuritySkillsData>(buildNamespaceSecuritySkillsUrl(namespaceId, params))
}

export function useNamespaceSecurityAnalytics(params: NamespaceSecurityAnalyticsParams) {
  return useQuery({
    queryKey: ['admin', 'namespace-security-analytics', params],
    queryFn: () => getNamespaceSecurityAnalytics(params),
  })
}

export function useNamespaceSecuritySkills(
  namespaceId: number | undefined,
  params: NamespaceSecuritySkillsParams,
) {
  return useQuery({
    queryKey: ['admin', 'namespace-security-analytics', 'namespace', namespaceId, params],
    queryFn: () => getNamespaceSecuritySkills(namespaceId!, params),
    enabled: namespaceId !== undefined,
  })
}

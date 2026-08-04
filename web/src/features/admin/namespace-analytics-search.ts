export type NamespaceAnalyticsNamespaceType = 'ALL' | 'TEAM' | 'GLOBAL'
export type NamespaceAnalyticsNamespaceStatus = 'ALL' | 'ACTIVE' | 'FROZEN' | 'ARCHIVED'
export type NamespaceAnalyticsPeriodPreset = '7d' | '30d' | '90d' | 'custom'
export type NamespaceAnalyticsSource = 'web' | 'cli' | 'api'
export type NamespaceAnalyticsSort =
  | 'namespace'
  | 'maintainers'
  | 'skills'
  | 'lifetimeDownloads'
  | 'periodDownloads'
export type NamespaceAnalyticsDirection = 'asc' | 'desc'

export interface NamespaceAnalyticsSearch {
  query?: string
  namespaceType: NamespaceAnalyticsNamespaceType
  namespaceStatus: NamespaceAnalyticsNamespaceStatus
  period: NamespaceAnalyticsPeriodPreset
  startTime?: string
  endTime?: string
  source?: NamespaceAnalyticsSource
  sort: NamespaceAnalyticsSort
  direction: NamespaceAnalyticsDirection
  page: number
  size: 20 | 50 | 100
}

const NAMESPACE_TYPES = ['ALL', 'TEAM', 'GLOBAL'] as const
const NAMESPACE_STATUSES = ['ALL', 'ACTIVE', 'FROZEN', 'ARCHIVED'] as const
const PERIODS = ['7d', '30d', '90d', 'custom'] as const
const SOURCES = ['web', 'cli', 'api'] as const
const SORTS = ['namespace', 'maintainers', 'skills', 'lifetimeDownloads', 'periodDownloads'] as const
const DIRECTIONS = ['asc', 'desc'] as const
const PAGE_SIZES = [20, 50, 100] as const
const DAY_MILLISECONDS = 24 * 60 * 60 * 1000

function enumValue<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === 'string' && allowed.includes(value as T) ? value as T : fallback
}

function optionalEnumValue<T extends string>(value: unknown, allowed: readonly T[]): T | undefined {
  return typeof value === 'string' && allowed.includes(value as T) ? value as T : undefined
}

function nonNegativeInteger(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : 0
}

function pageSize(value: unknown): 20 | 50 | 100 {
  const parsed = typeof value === 'number' ? value : Number(value)
  return PAGE_SIZES.includes(parsed as 20 | 50 | 100) ? parsed as 20 | 50 | 100 : 20
}

function optionalInstant(value: unknown): string | undefined {
  if (typeof value !== 'string' || Number.isNaN(new Date(value).getTime())) {
    return undefined
  }
  return value
}

export function parseNamespaceAnalyticsSearch(search: Record<string, unknown>): NamespaceAnalyticsSearch {
  const normalizedQuery = typeof search.query === 'string' ? search.query.trim() : ''
  return {
    query: normalizedQuery || undefined,
    namespaceType: enumValue(search.namespaceType, NAMESPACE_TYPES, 'ALL'),
    namespaceStatus: enumValue(search.namespaceStatus, NAMESPACE_STATUSES, 'ACTIVE'),
    period: enumValue(search.period, PERIODS, '30d'),
    startTime: optionalInstant(search.startTime),
    endTime: optionalInstant(search.endTime),
    source: optionalEnumValue(search.source, SOURCES),
    sort: enumValue(search.sort, SORTS, 'periodDownloads'),
    direction: enumValue(search.direction, DIRECTIONS, 'desc'),
    page: nonNegativeInteger(search.page),
    size: pageSize(search.size),
  }
}

export function resolveAnalyticsPeriod(
  search: NamespaceAnalyticsSearch,
  now: Date,
): { startTime: string; endTime: string } {
  if (search.period === 'custom' && search.startTime && search.endTime) {
    const customStart = new Date(search.startTime)
    const customEnd = new Date(search.endTime)
    if (customStart <= customEnd) {
      return {
        startTime: customStart.toISOString(),
        endTime: customEnd.toISOString(),
      }
    }
  }

  const days = search.period === '7d' ? 7 : search.period === '90d' ? 90 : 30
  const endTime = new Date(now)
  const startTime = new Date(endTime.getTime() - (days * DAY_MILLISECONDS))
  return {
    startTime: startTime.toISOString(),
    endTime: endTime.toISOString(),
  }
}

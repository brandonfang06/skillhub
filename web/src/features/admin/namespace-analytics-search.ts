export type NamespaceAnalyticsNamespaceType = 'ALL' | 'TEAM' | 'GLOBAL'
export type NamespaceAnalyticsNamespaceStatus = 'ALL' | 'ACTIVE' | 'FROZEN' | 'ARCHIVED'
export type NamespaceAnalyticsView = 'catalog' | 'security'
export type NamespaceAnalyticsPeriodPreset = '7d' | '30d' | '90d' | 'custom'
export type NamespaceAnalyticsSource = 'web' | 'cli' | 'api'
export type NamespaceAnalyticsSort =
  | 'namespace'
  | 'maintainers'
  | 'skills'
  | 'lifetimeDownloads'
  | 'periodDownloads'
export type NamespaceAnalyticsDirection = 'asc' | 'desc'
export type NamespaceSecuritySeverity = 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO' | 'UNCLASSIFIED'
export type NamespaceSecuritySkillStatus = 'ALL' | 'ACTIVE' | 'ARCHIVED'
export type NamespaceSecurityVisibility = 'ALL' | 'PUBLIC' | 'NAMESPACE_ONLY' | 'PRIVATE'
export type NamespaceSecurityHidden = 'ALL' | 'VISIBLE' | 'HIDDEN'
export type NamespaceSecurityVersionStatus =
  | 'ALL'
  | 'DRAFT'
  | 'SCANNING'
  | 'SCAN_FAILED'
  | 'UPLOADED'
  | 'PENDING_REVIEW'
  | 'PUBLISHED'
  | 'REJECTED'
  | 'YANKED'
export type NamespaceSecurityScannerType = 'skill-scanner' | 'custom'
export type NamespaceSecuritySort =
  | 'risk'
  | 'namespace'
  | 'affectedSkills'
  | 'affectedVersions'
  | 'findings'
  | 'latestScan'

export interface NamespaceAnalyticsSearch {
  view: NamespaceAnalyticsView
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
  severity?: NamespaceSecuritySeverity
  skillStatus?: NamespaceSecuritySkillStatus
  visibility?: NamespaceSecurityVisibility
  hidden?: NamespaceSecurityHidden
  versionStatus?: NamespaceSecurityVersionStatus
  scannerType?: NamespaceSecurityScannerType
  securitySort?: NamespaceSecuritySort
  securityDirection?: NamespaceAnalyticsDirection
  securityPage?: number
  securitySize?: 20 | 50 | 100
}

const VIEWS = ['catalog', 'security'] as const
const NAMESPACE_TYPES = ['ALL', 'TEAM', 'GLOBAL'] as const
const NAMESPACE_STATUSES = ['ALL', 'ACTIVE', 'FROZEN', 'ARCHIVED'] as const
const PERIODS = ['7d', '30d', '90d', 'custom'] as const
const SOURCES = ['web', 'cli', 'api'] as const
const SORTS = ['namespace', 'maintainers', 'skills', 'lifetimeDownloads', 'periodDownloads'] as const
const DIRECTIONS = ['asc', 'desc'] as const
const PAGE_SIZES = [20, 50, 100] as const
const SECURITY_SEVERITIES = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO', 'UNCLASSIFIED'] as const
const SECURITY_SKILL_STATUSES = ['ALL', 'ACTIVE', 'ARCHIVED'] as const
const SECURITY_VISIBILITIES = ['ALL', 'PUBLIC', 'NAMESPACE_ONLY', 'PRIVATE'] as const
const SECURITY_HIDDEN = ['ALL', 'VISIBLE', 'HIDDEN'] as const
const SECURITY_VERSION_STATUSES = [
  'ALL',
  'DRAFT',
  'SCANNING',
  'SCAN_FAILED',
  'UPLOADED',
  'PENDING_REVIEW',
  'PUBLISHED',
  'REJECTED',
  'YANKED',
] as const
const SECURITY_SCANNER_TYPES = ['skill-scanner', 'custom'] as const
const SECURITY_SORTS = [
  'risk',
  'namespace',
  'affectedSkills',
  'affectedVersions',
  'findings',
  'latestScan',
] as const
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
  const view = enumValue(search.view, VIEWS, 'catalog')
  const normalizedQuery = typeof search.query === 'string' ? search.query.trim() : ''
  const requestedPeriod = enumValue(search.period, PERIODS, '30d')
  const requestedStartTime = optionalInstant(search.startTime)
  const requestedEndTime = optionalInstant(search.endTime)
  const validCustomRange = requestedPeriod === 'custom'
    && requestedStartTime !== undefined
    && requestedEndTime !== undefined
    && new Date(requestedStartTime) <= new Date(requestedEndTime)
  const period = requestedPeriod === 'custom' && !validCustomRange ? '30d' : requestedPeriod
  const parsed: NamespaceAnalyticsSearch = {
    view,
    query: normalizedQuery || undefined,
    namespaceType: enumValue(search.namespaceType, NAMESPACE_TYPES, 'ALL'),
    namespaceStatus: enumValue(search.namespaceStatus, NAMESPACE_STATUSES, view === 'security' ? 'ALL' : 'ACTIVE'),
    period,
    startTime: period === 'custom' ? requestedStartTime : undefined,
    endTime: period === 'custom' ? requestedEndTime : undefined,
    source: optionalEnumValue(search.source, SOURCES),
    sort: enumValue(search.sort, SORTS, 'periodDownloads'),
    direction: enumValue(search.direction, DIRECTIONS, 'desc'),
    page: nonNegativeInteger(search.page),
    size: pageSize(search.size),
  }
  if (view === 'security') {
    return {
      ...parsed,
      severity: enumValue(search.severity, SECURITY_SEVERITIES, 'ALL'),
      skillStatus: enumValue(search.skillStatus, SECURITY_SKILL_STATUSES, 'ALL'),
      visibility: enumValue(search.visibility, SECURITY_VISIBILITIES, 'ALL'),
      hidden: enumValue(search.hidden, SECURITY_HIDDEN, 'ALL'),
      versionStatus: enumValue(search.versionStatus, SECURITY_VERSION_STATUSES, 'ALL'),
      scannerType: optionalEnumValue(search.scannerType, SECURITY_SCANNER_TYPES),
      securitySort: enumValue(search.securitySort, SECURITY_SORTS, 'risk'),
      securityDirection: enumValue(search.securityDirection, DIRECTIONS, 'desc'),
      securityPage: nonNegativeInteger(search.securityPage),
      securitySize: pageSize(search.securitySize),
    }
  }
  return parsed
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

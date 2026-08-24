import { Fragment, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, EyeOff, Filter, ShieldAlert } from 'lucide-react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import type {
  NamespaceSecurityAnalyticsParams,
  NamespaceSecuritySeverityCounts,
  NamespaceSecuritySkillItem,
  NamespaceSecuritySkillsParams,
  NamespaceSecurityVersionItem,
} from '@/api/types'
import {
  type NamespaceAnalyticsDirection,
  type NamespaceAnalyticsSearch,
  type NamespaceSecuritySort,
  parseNamespaceAnalyticsSearch,
} from './namespace-analytics-search'
import {
  useNamespaceSecurityAnalytics,
  useNamespaceSecuritySkills,
} from './use-namespace-security-analytics'
import { SecurityAuditSection } from '@/features/security-audit/security-audit-section'
import { NamespaceBadge } from '@/shared/components/namespace-badge'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/ui/table'

const ALL_SCANNERS = '__all_scanners__'
const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO', 'UNCLASSIFIED'] as const
const VERSION_STATUSES = [
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

const SEVERITY_KEYS = {
  CRITICAL: 'critical',
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low',
  INFO: 'info',
  UNCLASSIFIED: 'unclassified',
} as const satisfies Record<(typeof SEVERITIES)[number], keyof NamespaceSecuritySeverityCounts>

const SEVERITY_LABELS = {
  CRITICAL: 'namespaceSecurity.severityCritical',
  HIGH: 'namespaceSecurity.severityHigh',
  MEDIUM: 'namespaceSecurity.severityMedium',
  LOW: 'namespaceSecurity.severityLow',
  INFO: 'namespaceSecurity.severityInfo',
  UNCLASSIFIED: 'namespaceSecurity.severityUnclassified',
} as const

const SEVERITY_STYLES = {
  CRITICAL: 'border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-300',
  HIGH: 'border-orange-500/40 bg-orange-500/10 text-orange-600 dark:text-orange-300',
  MEDIUM: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  LOW: 'border-blue-500/40 bg-blue-500/10 text-blue-600 dark:text-blue-300',
  INFO: 'border-slate-500/40 bg-slate-500/10 text-slate-600 dark:text-slate-300',
  UNCLASSIFIED: 'border-purple-500/40 bg-purple-500/10 text-purple-600 dark:text-purple-300',
} as const

type SelectedVersion = {
  skill: NamespaceSecuritySkillItem
  version: NamespaceSecurityVersionItem
}

function SeverityBadge({ severity }: { severity: (typeof SEVERITIES)[number] }) {
  const { t } = useTranslation()
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${SEVERITY_STYLES[severity]}`}>
      {t(SEVERITY_LABELS[severity])}
    </span>
  )
}

function SeverityDistribution({ counts }: { counts: NamespaceSecuritySeverityCounts }) {
  return (
    <div className="flex min-w-56 flex-wrap gap-1.5">
      {SEVERITIES.map((severity) => {
        const count = counts[SEVERITY_KEYS[severity]]
        return count > 0 ? (
          <span
            key={severity}
            className={`rounded-full border px-2 py-0.5 text-xs ${SEVERITY_STYLES[severity]}`}
          >
            {severity.slice(0, 1)} {count}
          </span>
        ) : null
      })}
    </div>
  )
}

function lifecycleClassName(status: string): string {
  if (status === 'ACTIVE' || status === 'PUBLISHED') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300'
  }
  if (status === 'ARCHIVED' || status === 'YANKED' || status === 'REJECTED') {
    return 'border-border bg-muted text-muted-foreground'
  }
  return 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'
}

function LifecycleBadge({ value }: { value: string }) {
  return <span className={`rounded-full border px-2 py-0.5 text-xs ${lifecycleClassName(value)}`}>{value}</span>
}

function NamespaceSkillRows({
  skills,
  onSelectVersion,
}: {
  skills: NamespaceSecuritySkillItem[]
  onSelectVersion: (selection: SelectedVersion) => void
}) {
  const { t, i18n } = useTranslation()
  return (
    <div className="space-y-4 bg-muted/20 p-4">
      {skills.map((skill) => (
        <Card key={skill.skillId} className="p-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 space-y-2">
              <div className="font-semibold">{skill.displayName}</div>
              <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                <span>@{skill.slug}</span>
                <LifecycleBadge value={skill.status} />
                <span className="rounded-full border border-border px-2 py-0.5 text-xs">{skill.visibility}</span>
                {skill.hidden ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs">
                    <EyeOff className="h-3 w-3" aria-hidden="true" />
                    {t('namespaceSecurity.hidden')}
                  </span>
                ) : null}
              </div>
              <div className="text-sm text-muted-foreground">
                <span>{t('namespaceSecurity.owner')}: </span>
                <span>{skill.ownerDisplayName || skill.ownerId}</span>
              </div>
            </div>
            <div className="space-y-2 text-right text-sm">
              <SeverityBadge severity={skill.maxSeverity} />
              <div>{t('namespaceSecurity.findingInstances', { count: skill.findingCount })}</div>
              <div className="text-muted-foreground">
                {formatLocalDateTime(skill.latestScanAt, i18n.language)}
              </div>
            </div>
          </div>
          <div className="mt-4 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('namespaceSecurity.colVersion')}</TableHead>
                  <TableHead>{t('namespaceSecurity.colVersionStatus')}</TableHead>
                  <TableHead>{t('namespaceSecurity.colScanners')}</TableHead>
                  <TableHead>{t('namespaceSecurity.colSeverity')}</TableHead>
                  <TableHead>{t('namespaceSecurity.colFindings')}</TableHead>
                  <TableHead>{t('namespaceSecurity.colLatestScan')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skill.versions.map((version) => (
                  <TableRow key={version.versionId}>
                    <TableCell>
                      <Button variant="link" className="px-0" onClick={() => onSelectVersion({ skill, version })}>
                        {version.version}
                      </Button>
                    </TableCell>
                    <TableCell><LifecycleBadge value={version.status} /></TableCell>
                    <TableCell>{version.scannerTypes.join(', ')}</TableCell>
                    <TableCell><SeverityBadge severity={version.maxSeverity} /></TableCell>
                    <TableCell>{version.findingCount}</TableCell>
                    <TableCell>{formatLocalDateTime(version.latestScanAt, i18n.language)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      ))}
    </div>
  )
}

export function NamespaceSecurityAnalyticsView() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate({ from: '/admin/namespace-analytics' })
  const rawSearch = useSearch({ from: '/admin/namespace-analytics' }) as Record<string, unknown>
  const search = useMemo(() => parseNamespaceAnalyticsSearch(rawSearch), [rawSearch])
  const [queryDraft, setQueryDraft] = useState(search.query ?? '')
  const [showMoreFilters, setShowMoreFilters] = useState(false)
  const [expandedNamespaceId, setExpandedNamespaceId] = useState<number>()
  const [skillPage, setSkillPage] = useState(0)
  const [selectedVersion, setSelectedVersion] = useState<SelectedVersion>()

  const params: NamespaceSecurityAnalyticsParams = {
    query: search.query,
    severity: search.severity ?? 'ALL',
    namespaceType: search.namespaceType,
    namespaceStatus: search.namespaceStatus,
    skillStatus: search.skillStatus ?? 'ALL',
    visibility: search.visibility ?? 'ALL',
    hidden: search.hidden ?? 'ALL',
    versionStatus: search.versionStatus ?? 'ALL',
    scannerType: search.scannerType,
    sort: search.securitySort ?? 'risk',
    direction: search.securityDirection ?? 'desc',
    page: search.securityPage ?? 0,
    size: search.securitySize ?? 20,
  }
  const skillParams: NamespaceSecuritySkillsParams = {
    query: params.query,
    severity: params.severity,
    skillStatus: params.skillStatus,
    visibility: params.visibility,
    hidden: params.hidden,
    versionStatus: params.versionStatus,
    scannerType: params.scannerType,
    sort: 'risk',
    direction: params.direction,
    page: skillPage,
    size: 20,
  }
  const { data, isLoading, isError, refetch } = useNamespaceSecurityAnalytics(params)
  const skillQuery = useNamespaceSecuritySkills(expandedNamespaceId, skillParams)
  const numberFormatter = useMemo(() => new Intl.NumberFormat(i18n.language), [i18n.language])

  const updateSearch = (patch: Partial<NamespaceAnalyticsSearch>, resetPage = true) => {
    setSkillPage(0)
    navigate({
      search: {
        ...search,
        ...patch,
        securityPage: resetPage ? 0 : patch.securityPage ?? search.securityPage,
      },
    })
  }

  const commitQuery = () => {
    const query = queryDraft.trim() || undefined
    if (query !== search.query) updateSearch({ query })
  }

  const updateSort = (sort: NamespaceSecuritySort) => {
    const direction: NamespaceAnalyticsDirection = search.securitySort === sort
      && search.securityDirection === 'desc' ? 'asc' : 'desc'
    updateSearch({ securitySort: sort, securityDirection: direction })
  }

  const clearFilters = () => {
    setQueryDraft('')
    navigate({
      search: {
        view: 'security',
        namespaceType: 'ALL',
        namespaceStatus: 'ALL',
        period: '30d',
        sort: 'periodDownloads',
        direction: 'desc',
        page: 0,
        size: 20,
        severity: 'ALL',
        skillStatus: 'ALL',
        visibility: 'ALL',
        hidden: 'ALL',
        versionStatus: 'ALL',
        securitySort: 'risk',
        securityDirection: 'desc',
        securityPage: 0,
        securitySize: 20,
      },
    })
  }

  if (isLoading) {
    return (
      <div data-testid="namespace-security-loading" className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-28 animate-shimmer rounded-xl" />
          ))}
        </div>
        <div className="h-96 animate-shimmer rounded-xl" />
      </div>
    )
  }

  if (isError) {
    return (
      <Card className="p-12 text-center">
        <h2 className="text-xl font-semibold">{t('namespaceSecurity.errorTitle')}</h2>
        <p className="mt-2 text-muted-foreground">{t('namespaceSecurity.errorDescription')}</p>
        <Button className="mt-5" onClick={() => refetch()}>{t('namespaceAnalytics.retry')}</Button>
      </Card>
    )
  }

  if (!data) return null

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {([
          ['affectedNamespaceCount', 'namespaceSecurity.summaryNamespaces'],
          ['affectedSkillCount', 'namespaceSecurity.summarySkills'],
          ['affectedVersionCount', 'namespaceSecurity.summaryVersions'],
          ['findingCount', 'namespaceSecurity.summaryFindings'],
        ] as const).map(([field, label]) => (
          <Card key={field} className="p-5">
            <div className="text-sm text-muted-foreground">{t(label)}</div>
            <div className="mt-3 text-3xl font-semibold font-heading">
              {numberFormatter.format(data.summary[field])}
            </div>
          </Card>
        ))}
      </div>

      <Card className="p-5">
        <div className="flex flex-wrap gap-2">
          {SEVERITIES.map((severity) => (
            <Button
              key={severity}
              variant={search.severity === severity ? 'default' : 'outline'}
              size="sm"
              aria-label={t(SEVERITY_LABELS[severity])}
              onClick={() => updateSearch({ severity })}
            >
              {t(SEVERITY_LABELS[severity])}: {numberFormatter.format(data.summary.severityCounts[SEVERITY_KEYS[severity]])}
            </Button>
          ))}
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Input
            className="xl:col-span-2"
            placeholder={t('namespaceSecurity.searchPlaceholder')}
            value={queryDraft}
            onChange={(event) => setQueryDraft(event.target.value)}
            onBlur={commitQuery}
            onKeyDown={(event) => {
              if (event.key === 'Enter') commitQuery()
            }}
          />
          <Select value={search.severity ?? 'ALL'} onValueChange={(value) => updateSearch({
            severity: value as NamespaceAnalyticsSearch['severity'],
          })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">{t('namespaceSecurity.severityAll')}</SelectItem>
              {SEVERITIES.map((severity) => (
                <SelectItem key={severity} value={severity}>{t(SEVERITY_LABELS[severity])}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={search.visibility ?? 'ALL'} onValueChange={(value) => updateSearch({
            visibility: value as NamespaceAnalyticsSearch['visibility'],
          })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">{t('namespaceSecurity.visibilityAll')}</SelectItem>
              <SelectItem value="PUBLIC">PUBLIC</SelectItem>
              <SelectItem value="NAMESPACE_ONLY">NAMESPACE_ONLY</SelectItem>
              <SelectItem value="PRIVATE">PRIVATE</SelectItem>
            </SelectContent>
          </Select>
          <Select value={search.versionStatus ?? 'ALL'} onValueChange={(value) => updateSearch({
            versionStatus: value as NamespaceAnalyticsSearch['versionStatus'],
          })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {VERSION_STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  {status === 'ALL' ? t('namespaceSecurity.versionStatusAll') : status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <Button variant="ghost" size="sm" onClick={() => setShowMoreFilters((value) => !value)}>
            <Filter className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('namespaceSecurity.moreFilters')}
          </Button>
          <Button variant="outline" size="sm" onClick={clearFilters}>{t('namespaceAnalytics.clearFilters')}</Button>
        </div>
        {showMoreFilters ? (
          <div className="mt-4 grid gap-4 border-t border-border/60 pt-4 md:grid-cols-2 xl:grid-cols-5">
            <Select value={search.namespaceType} onValueChange={(value) => updateSearch({
              namespaceType: value as NamespaceAnalyticsSearch['namespaceType'],
            })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">{t('namespaceAnalytics.namespaceTypeAll')}</SelectItem>
                <SelectItem value="TEAM">TEAM</SelectItem>
                <SelectItem value="GLOBAL">GLOBAL</SelectItem>
              </SelectContent>
            </Select>
            <Select value={search.namespaceStatus} onValueChange={(value) => updateSearch({
              namespaceStatus: value as NamespaceAnalyticsSearch['namespaceStatus'],
            })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">{t('namespaceAnalytics.namespaceStatusAll')}</SelectItem>
                <SelectItem value="ACTIVE">ACTIVE</SelectItem>
                <SelectItem value="FROZEN">FROZEN</SelectItem>
                <SelectItem value="ARCHIVED">ARCHIVED</SelectItem>
              </SelectContent>
            </Select>
            <Select value={search.skillStatus ?? 'ALL'} onValueChange={(value) => updateSearch({
              skillStatus: value as NamespaceAnalyticsSearch['skillStatus'],
            })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">{t('namespaceSecurity.skillStatusAll')}</SelectItem>
                <SelectItem value="ACTIVE">ACTIVE</SelectItem>
                <SelectItem value="ARCHIVED">ARCHIVED</SelectItem>
              </SelectContent>
            </Select>
            <Select value={search.hidden ?? 'ALL'} onValueChange={(value) => updateSearch({
              hidden: value as NamespaceAnalyticsSearch['hidden'],
            })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">{t('namespaceSecurity.hiddenAll')}</SelectItem>
                <SelectItem value="VISIBLE">{t('namespaceSecurity.visibleOnly')}</SelectItem>
                <SelectItem value="HIDDEN">{t('namespaceSecurity.hiddenOnly')}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={search.scannerType ?? ALL_SCANNERS} onValueChange={(value) => updateSearch({
              scannerType: value === ALL_SCANNERS ? undefined : value as NamespaceAnalyticsSearch['scannerType'],
            })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_SCANNERS}>{t('namespaceSecurity.scannerAll')}</SelectItem>
                <SelectItem value="skill-scanner">skill-scanner</SelectItem>
                <SelectItem value="custom">custom</SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : null}
      </Card>

      {data.items.length === 0 ? (
        <Card className="p-12 text-center">
          <ShieldAlert className="mx-auto h-9 w-9 text-muted-foreground" aria-hidden="true" />
          <h2 className="mt-4 text-xl font-semibold">{t('namespaceSecurity.emptyTitle')}</h2>
          <p className="mt-2 text-muted-foreground">{t('namespaceSecurity.emptyDescription')}</p>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead><span className="sr-only">{t('namespaceSecurity.expandNamespace')}</span></TableHead>
                  <TableHead>
                    <Button variant="ghost" size="sm" onClick={() => updateSort('namespace')}>
                      {t('namespaceAnalytics.colNamespace')}
                    </Button>
                  </TableHead>
                  <TableHead>{t('namespaceSecurity.colAffectedSkills')}</TableHead>
                  <TableHead>{t('namespaceSecurity.colAffectedVersions')}</TableHead>
                  <TableHead>{t('namespaceSecurity.colMaxSeverity')}</TableHead>
                  <TableHead>{t('namespaceSecurity.colDistribution')}</TableHead>
                  <TableHead>
                    <Button variant="ghost" size="sm" onClick={() => updateSort('findings')}>
                      {t('namespaceSecurity.colFindings')}
                    </Button>
                  </TableHead>
                  <TableHead>
                    <Button variant="ghost" size="sm" onClick={() => updateSort('latestScan')}>
                      {t('namespaceSecurity.colLatestScan')}
                    </Button>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((item) => {
                  const expanded = item.namespaceId === expandedNamespaceId
                  return (
                    <Fragment key={item.namespaceId}>
                      <TableRow>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={t(expanded ? 'namespaceSecurity.collapseNamespace' : 'namespaceSecurity.expandNamespace')}
                            onClick={() => {
                              setSkillPage(0)
                              setExpandedNamespaceId(expanded ? undefined : item.namespaceId)
                            }}
                          >
                            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                          </Button>
                        </TableCell>
                        <TableCell>
                          <div className="min-w-48 space-y-2">
                            <div className="font-medium">{item.displayName}</div>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm text-muted-foreground">@{item.slug}</span>
                              <NamespaceBadge type={item.type} name={item.type} className="px-2 py-0.5" />
                              <LifecycleBadge value={item.status} />
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>{item.affectedSkillCount}</TableCell>
                        <TableCell>{item.affectedVersionCount}</TableCell>
                        <TableCell><SeverityBadge severity={item.maxSeverity} /></TableCell>
                        <TableCell><SeverityDistribution counts={item.severityCounts} /></TableCell>
                        <TableCell className="font-semibold">{item.findingCount}</TableCell>
                        <TableCell>{formatLocalDateTime(item.latestScanAt, i18n.language)}</TableCell>
                      </TableRow>
                      {expanded ? (
                        <TableRow key={`${item.namespaceId}-skills`}>
                          <TableCell colSpan={8} className="p-0">
                            {skillQuery.isLoading ? (
                              <div className="h-32 animate-shimmer" />
                            ) : skillQuery.isError ? (
                              <div className="p-6 text-center text-sm text-destructive">
                                {t('namespaceSecurity.skillLoadError')}
                              </div>
                            ) : skillQuery.data ? (
                              <>
                                <NamespaceSkillRows skills={skillQuery.data.items} onSelectVersion={setSelectedVersion} />
                                {skillQuery.data.total > skillQuery.data.size ? (
                                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 p-4">
                                    <p className="text-sm text-muted-foreground">
                                      {t('namespaceSecurity.totalSkills', { total: skillQuery.data.total })}
                                    </p>
                                    <div className="flex gap-2">
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        aria-label={t('namespaceSecurity.previousSkillsPage')}
                                        disabled={skillPage === 0}
                                        onClick={() => setSkillPage((page) => Math.max(0, page - 1))}
                                      >
                                        {t('namespaceAnalytics.previousPage')}
                                      </Button>
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        aria-label={t('namespaceSecurity.nextSkillsPage')}
                                        disabled={(skillPage + 1) * skillQuery.data.size >= skillQuery.data.total}
                                        onClick={() => setSkillPage((page) => page + 1)}
                                      >
                                        {t('namespaceAnalytics.nextPage')}
                                      </Button>
                                    </div>
                                  </div>
                                ) : null}
                              </>
                            ) : null}
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{t('namespaceSecurity.totalNamespaces', { total: data.total })}</p>
        <div className="flex items-center gap-2">
          <Select value={String(search.securitySize ?? 20)} onValueChange={(value) => updateSearch({
            securitySize: Number(value) as NamespaceAnalyticsSearch['securitySize'],
          })}>
            <SelectTrigger className="w-28" aria-label={t('namespaceAnalytics.pageSize')}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="20">20</SelectItem>
              <SelectItem value="50">50</SelectItem>
              <SelectItem value="100">100</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            disabled={(search.securityPage ?? 0) === 0}
            onClick={() => updateSearch({ securityPage: Math.max(0, (search.securityPage ?? 0) - 1) }, false)}
          >
            {t('namespaceAnalytics.previousPage')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={((search.securityPage ?? 0) + 1) * (search.securitySize ?? 20) >= data.total}
            onClick={() => updateSearch({ securityPage: (search.securityPage ?? 0) + 1 }, false)}
          >
            {t('namespaceAnalytics.nextPage')}
          </Button>
        </div>
      </div>

      <Dialog open={selectedVersion !== undefined} onOpenChange={(open) => {
        if (!open) setSelectedVersion(undefined)
      }}>
        {selectedVersion ? (
          <DialogContent className="w-[min(calc(100vw-2rem),64rem)]">
            <DialogHeader>
              <DialogTitle>{selectedVersion.skill.displayName} · {selectedVersion.version.version}</DialogTitle>
              <DialogDescription>{t('namespaceSecurity.detailDescription')}</DialogDescription>
            </DialogHeader>
            <SecurityAuditSection
              skillId={selectedVersion.skill.skillId}
              versionId={selectedVersion.version.versionId}
              versionStatus={selectedVersion.version.status}
              bare
            />
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  )
}

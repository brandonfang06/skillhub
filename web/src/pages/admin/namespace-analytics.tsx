import { useMemo } from 'react'
import { ArrowUpDown } from 'lucide-react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import type { NamespaceAnalyticsItem, NamespaceAnalyticsParams } from '@/api/types'
import {
  type NamespaceAnalyticsDirection,
  type NamespaceAnalyticsSearch,
  type NamespaceAnalyticsSort,
  parseNamespaceAnalyticsSearch,
  resolveAnalyticsPeriod,
} from '@/features/admin/namespace-analytics-search'
import { useNamespaceAnalytics } from '@/features/admin/use-namespace-analytics'
import { NamespaceBadge } from '@/shared/components/namespace-badge'
import { toLocalDateTimeInputValue } from '@/shared/lib/date-time'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
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

const CLEAR_SEARCH = {
  namespaceType: 'ALL',
  namespaceStatus: 'ACTIVE',
  period: '30d',
  sort: 'periodDownloads',
  direction: 'desc',
  page: 0,
  size: 20,
} as const

const ALL_SOURCES = '__all_sources__'

const SUMMARY_FIELDS = [
  ['namespaceCount', 'namespaceAnalytics.summaryNamespaces'],
  ['maintainerCount', 'namespaceAnalytics.summaryMaintainers'],
  ['skillCount', 'namespaceAnalytics.summarySkills'],
  ['lifetimeDownloads', 'namespaceAnalytics.summaryLifetimeDownloads'],
  ['periodDownloads', 'namespaceAnalytics.summaryPeriodDownloads'],
] as const

const SORT_COLUMNS: Array<{ key: NamespaceAnalyticsSort; label: string }> = [
  { key: 'namespace', label: 'namespaceAnalytics.colNamespace' },
  { key: 'maintainers', label: 'namespaceAnalytics.colMaintainers' },
  { key: 'skills', label: 'namespaceAnalytics.colSkills' },
  { key: 'lifetimeDownloads', label: 'namespaceAnalytics.colLifetimeDownloads' },
  { key: 'periodDownloads', label: 'namespaceAnalytics.colPeriodDownloads' },
]

function localInputToInstant(value: string): string | undefined {
  if (!value) {
    return undefined
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString()
}

function statusClassName(status: string): string {
  if (status === 'ACTIVE') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-500'
  if (status === 'FROZEN') return 'border-amber-500/30 bg-amber-500/10 text-amber-500'
  return 'border-border bg-muted text-muted-foreground'
}

function namespaceType(item: NamespaceAnalyticsItem): 'GLOBAL' | 'TEAM' {
  return item.type === 'GLOBAL' ? 'GLOBAL' : 'TEAM'
}

export function NamespaceAnalyticsPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate({ from: '/admin/namespace-analytics' })
  const rawSearch = useSearch({ from: '/admin/namespace-analytics' }) as Record<string, unknown>
  const search = useMemo(() => parseNamespaceAnalyticsSearch(rawSearch), [rawSearch])
  const stableNow = useMemo(() => new Date(), [])
  const selectedPeriod = useMemo(() => resolveAnalyticsPeriod(search, stableNow), [search, stableNow])
  const params: NamespaceAnalyticsParams = {
    query: search.query,
    namespaceType: search.namespaceType,
    namespaceStatus: search.namespaceStatus,
    startTime: selectedPeriod.startTime,
    endTime: selectedPeriod.endTime,
    source: search.source,
    sort: search.sort,
    direction: search.direction,
    page: search.page,
    size: search.size,
  }
  const { data, isLoading, isError, refetch } = useNamespaceAnalytics(params)
  const numberFormatter = useMemo(() => new Intl.NumberFormat(i18n.language), [i18n.language])

  const updateSearch = (patch: Partial<NamespaceAnalyticsSearch>, resetPage = true) => {
    navigate({
      search: {
        ...search,
        ...patch,
        page: resetPage ? 0 : patch.page ?? search.page,
      },
    })
  }

  const updateSort = (sort: NamespaceAnalyticsSort) => {
    const direction: NamespaceAnalyticsDirection = search.sort === sort && search.direction === 'desc' ? 'asc' : 'desc'
    updateSearch({ sort, direction })
  }

  const selectPeriod = (period: NamespaceAnalyticsSearch['period']) => {
    if (period === 'custom') {
      updateSearch({
        period,
        startTime: selectedPeriod.startTime,
        endTime: selectedPeriod.endTime,
      })
      return
    }
    updateSearch({ period, startTime: undefined, endTime: undefined })
  }

  const viewEvents = (item: NamespaceAnalyticsItem) => {
    if (!data) return
    navigate({
      to: '/admin/download-events',
      search: {
        namespace: item.slug,
        startTime: data.period.startTime,
        endTime: data.period.endTime,
        source: data.period.source ?? undefined,
      },
    })
  }

  return (
    <div className="space-y-8 animate-fade-up">
      <div>
        <h1 className="mb-2 text-4xl font-bold font-heading">{t('namespaceAnalytics.title')}</h1>
        <p className="max-w-4xl text-lg text-muted-foreground">{t('namespaceAnalytics.subtitle')}</p>
      </div>

      {isLoading ? (
        <div data-testid="namespace-analytics-loading" className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, index) => (
              <div key={index} className="h-28 animate-shimmer rounded-xl" />
            ))}
          </div>
          <div className="h-80 animate-shimmer rounded-xl" />
        </div>
      ) : isError ? (
        <Card className="p-12 text-center">
          <h2 className="text-xl font-semibold">{t('namespaceAnalytics.errorTitle')}</h2>
          <p className="mt-2 text-muted-foreground">{t('namespaceAnalytics.errorDescription')}</p>
          <Button className="mt-5" onClick={() => refetch()}>{t('namespaceAnalytics.retry')}</Button>
        </Card>
      ) : data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {SUMMARY_FIELDS.map(([field, label]) => (
              <Card key={field} className="p-5">
                <div className="text-sm text-muted-foreground">{t(label)}</div>
                <div className="mt-3 text-3xl font-semibold font-heading">
                  {numberFormatter.format(data.summary[field])}
                </div>
              </Card>
            ))}
          </div>

          <Card className="p-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <Input
                className="xl:col-span-2"
                placeholder={t('namespaceAnalytics.searchPlaceholder')}
                value={search.query ?? ''}
                onChange={(event) => updateSearch({ query: event.target.value.trim() || undefined })}
              />
              <Select value={search.namespaceType} onValueChange={(value) => updateSearch({
                namespaceType: value as NamespaceAnalyticsSearch['namespaceType'],
              })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">{t('namespaceAnalytics.namespaceTypeAll')}</SelectItem>
                  <SelectItem value="TEAM">{t('namespaceAnalytics.namespaceTypeTeam')}</SelectItem>
                  <SelectItem value="GLOBAL">{t('namespaceAnalytics.namespaceTypeGlobal')}</SelectItem>
                </SelectContent>
              </Select>
              <Select value={search.namespaceStatus} onValueChange={(value) => updateSearch({
                namespaceStatus: value as NamespaceAnalyticsSearch['namespaceStatus'],
              })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">{t('namespaceAnalytics.namespaceStatusAll')}</SelectItem>
                  <SelectItem value="ACTIVE">{t('namespaceAnalytics.namespaceStatusActive')}</SelectItem>
                  <SelectItem value="FROZEN">{t('namespaceAnalytics.namespaceStatusFrozen')}</SelectItem>
                  <SelectItem value="ARCHIVED">{t('namespaceAnalytics.namespaceStatusArchived')}</SelectItem>
                </SelectContent>
              </Select>
              <Select value={search.period} onValueChange={(value) => selectPeriod(value as NamespaceAnalyticsSearch['period'])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="7d">{t('namespaceAnalytics.period7Days')}</SelectItem>
                  <SelectItem value="30d">{t('namespaceAnalytics.period30Days')}</SelectItem>
                  <SelectItem value="90d">{t('namespaceAnalytics.period90Days')}</SelectItem>
                  <SelectItem value="custom">{t('namespaceAnalytics.periodCustom')}</SelectItem>
                </SelectContent>
              </Select>
              <Select value={search.source ?? ALL_SOURCES} onValueChange={(value) => updateSearch({
                source: value === ALL_SOURCES ? undefined : value as NamespaceAnalyticsSearch['source'],
              })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_SOURCES}>{t('namespaceAnalytics.sourceAll')}</SelectItem>
                  <SelectItem value="web">{t('namespaceAnalytics.sourceWeb')}</SelectItem>
                  <SelectItem value="cli">{t('namespaceAnalytics.sourceCli')}</SelectItem>
                  <SelectItem value="api">{t('namespaceAnalytics.sourceApi')}</SelectItem>
                </SelectContent>
              </Select>
              {search.period === 'custom' ? (
                <>
                  <Input
                    aria-label={t('namespaceAnalytics.customStart')}
                    type="datetime-local"
                    value={search.startTime ? toLocalDateTimeInputValue(search.startTime) : ''}
                    onChange={(event) => updateSearch({ startTime: localInputToInstant(event.target.value) })}
                  />
                  <Input
                    aria-label={t('namespaceAnalytics.customEnd')}
                    type="datetime-local"
                    value={search.endTime ? toLocalDateTimeInputValue(search.endTime) : ''}
                    onChange={(event) => updateSearch({ endTime: localInputToInstant(event.target.value) })}
                  />
                </>
              ) : null}
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                {t('namespaceAnalytics.retentionNote', { months: data.period.retentionMonths })}
              </p>
              <Button variant="outline" size="sm" onClick={() => navigate({ search: CLEAR_SEARCH })}>
                {t('namespaceAnalytics.clearFilters')}
              </Button>
            </div>
          </Card>

          {data.items.length === 0 ? (
            <Card className="p-12 text-center">
              <h2 className="text-xl font-semibold">{t('namespaceAnalytics.emptyTitle')}</h2>
              <p className="mt-2 text-muted-foreground">{t('namespaceAnalytics.emptyDescription')}</p>
              <Button className="mt-5" variant="outline" onClick={() => navigate({ search: CLEAR_SEARCH })}>
                {t('namespaceAnalytics.clearFilters')}
              </Button>
            </Card>
          ) : (
            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {SORT_COLUMNS.map((column) => (
                        <TableHead key={column.key}>
                          <Button variant="ghost" size="sm" onClick={() => updateSort(column.key)}>
                            {t(column.label)}
                            <ArrowUpDown className="ml-2 h-3.5 w-3.5" aria-hidden="true" />
                          </Button>
                        </TableHead>
                      ))}
                      <TableHead><span className="sr-only">{t('namespaceAnalytics.viewEvents')}</span></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((item) => (
                      <TableRow key={item.namespaceId}>
                        <TableCell>
                          <div className="min-w-48 space-y-2">
                            <div className="font-medium">{item.displayName}</div>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm text-muted-foreground">@{item.slug}</span>
                              <NamespaceBadge type={namespaceType(item)} name={item.type} className="px-2 py-0.5" />
                              <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClassName(item.status)}`}>
                                {item.status}
                              </span>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>{numberFormatter.format(item.maintainerCount)}</TableCell>
                        <TableCell>{numberFormatter.format(item.skillCount)}</TableCell>
                        <TableCell>{numberFormatter.format(item.lifetimeDownloads)}</TableCell>
                        <TableCell className="font-semibold">{numberFormatter.format(item.periodDownloads)}</TableCell>
                        <TableCell>
                          <Button variant="outline" size="sm" onClick={() => viewEvents(item)}>
                            {t('namespaceAnalytics.viewEvents')}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </Card>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {t('namespaceAnalytics.totalNamespaces', { total: data.total })}
            </p>
            <div className="flex items-center gap-2">
              <Select value={String(search.size)} onValueChange={(value) => updateSearch({
                size: Number(value) as NamespaceAnalyticsSearch['size'],
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
                disabled={search.page === 0}
                onClick={() => updateSearch({ page: Math.max(0, search.page - 1) }, false)}
              >
                {t('namespaceAnalytics.previousPage')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(search.page + 1) * search.size >= data.total}
                onClick={() => updateSearch({ page: search.page + 1 }, false)}
              >
                {t('namespaceAnalytics.nextPage')}
              </Button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}

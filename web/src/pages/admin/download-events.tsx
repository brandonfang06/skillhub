import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { Card } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import { Button } from '@/shared/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  normalizeSelectValue,
} from '@/shared/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/ui/table'
import { useDownloadEvents } from '@/features/admin/use-download-events'

const SOURCE_OPTIONS = [
  { value: '', labelKey: 'downloadEvents.filterAllSources' },
  { value: 'web', labelKey: 'downloadEvents.sourceWeb' },
  { value: 'cli', labelKey: 'downloadEvents.sourceCli' },
  { value: 'api', labelKey: 'downloadEvents.sourceApi' },
] as const

export function DownloadEventsPage() {
  const { t, i18n } = useTranslation()
  const allSourceFilterValue = '__all_sources__'
  const [namespaceFilter, setNamespaceFilter] = useState('')
  const [slugFilter, setSlugFilter] = useState('')
  const [versionFilter, setVersionFilter] = useState('')
  const [userIdFilter, setUserIdFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [startTimeFilter, setStartTimeFilter] = useState('')
  const [endTimeFilter, setEndTimeFilter] = useState('')
  const [page, setPage] = useState(0)

  const { data, isLoading } = useDownloadEvents({
    namespace: namespaceFilter.trim() || undefined,
    slug: slugFilter.trim() || undefined,
    version: versionFilter.trim() || undefined,
    userId: userIdFilter.trim() || undefined,
    source: sourceFilter || undefined,
    startTime: startTimeFilter ? new Date(startTimeFilter).toISOString() : undefined,
    endTime: endTimeFilter ? new Date(endTimeFilter).toISOString() : undefined,
    page,
    size: 20,
  })

  const clearFilters = () => {
    setNamespaceFilter('')
    setSlugFilter('')
    setVersionFilter('')
    setUserIdFilter('')
    setSourceFilter('')
    setStartTimeFilter('')
    setEndTimeFilter('')
    setPage(0)
  }

  const formatDate = (dateString: string) => {
    return formatLocalDateTime(dateString, i18n.language)
  }

  return (
    <div className="space-y-8 animate-fade-up">
      <div>
        <h1 className="text-4xl font-bold font-heading mb-2">{t('downloadEvents.title')}</h1>
        <p className="text-muted-foreground text-lg">{t('downloadEvents.subtitle')}</p>
      </div>

      <Card className="p-5">
        <div className="mb-4 flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={clearFilters}>
            {t('downloadEvents.clearFilters')}
          </Button>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Input
            placeholder={t('downloadEvents.namespacePlaceholder')}
            value={namespaceFilter}
            onChange={(event) => {
              setNamespaceFilter(event.target.value)
              setPage(0)
            }}
          />
          <Input
            placeholder={t('downloadEvents.slugPlaceholder')}
            value={slugFilter}
            onChange={(event) => {
              setSlugFilter(event.target.value)
              setPage(0)
            }}
          />
          <Input
            placeholder={t('downloadEvents.versionPlaceholder')}
            value={versionFilter}
            onChange={(event) => {
              setVersionFilter(event.target.value)
              setPage(0)
            }}
          />
          <Input
            placeholder={t('downloadEvents.userIdPlaceholder')}
            value={userIdFilter}
            onChange={(event) => {
              setUserIdFilter(event.target.value)
              setPage(0)
            }}
          />
          <Select
            value={normalizeSelectValue(sourceFilter) ?? allSourceFilterValue}
            onValueChange={(value) => {
              setSourceFilter(value === allSourceFilterValue ? '' : value)
              setPage(0)
            }}
          >
            <SelectTrigger className="w-[200px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SOURCE_OPTIONS.map((option) => (
                <SelectItem
                  key={option.value || allSourceFilterValue}
                  value={option.value || allSourceFilterValue}
                >
                  {t(option.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="datetime-local"
            value={startTimeFilter}
            onChange={(event) => {
              setStartTimeFilter(event.target.value)
              setPage(0)
            }}
          />
          <Input
            type="datetime-local"
            value={endTimeFilter}
            onChange={(event) => {
              setEndTimeFilter(event.target.value)
              setPage(0)
            }}
          />
        </div>
      </Card>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-14 animate-shimmer rounded-lg" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <Card className="p-12 text-center">
          <p className="text-muted-foreground">{t('downloadEvents.empty')}</p>
        </Card>
      ) : (
        <>
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('downloadEvents.colTime')}</TableHead>
                  <TableHead>{t('downloadEvents.colUser')}</TableHead>
                  <TableHead>{t('downloadEvents.colSkill')}</TableHead>
                  <TableHead>{t('downloadEvents.colVersion')}</TableHead>
                  <TableHead>{t('downloadEvents.colSource')}</TableHead>
                  <TableHead>{t('downloadEvents.colIp')}</TableHead>
                  <TableHead>{t('downloadEvents.colUserAgent')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((event) => (
                  <TableRow key={event.id}>
                    <TableCell>{formatDate(event.createdAt)}</TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <div className="font-medium">{event.userId || t('downloadEvents.anonymousUser')}</div>
                        {event.username ? (
                          <div className="text-xs text-muted-foreground">{event.username}</div>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="font-medium">{event.namespace}/{event.slug}</TableCell>
                    <TableCell>{event.version}</TableCell>
                    <TableCell>{event.source}</TableCell>
                    <TableCell>{event.ipAddress || '-'}</TableCell>
                    <TableCell className="max-w-xs truncate">{event.userAgent || '-'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>

          <div className="flex justify-between items-center">
            <p className="text-sm text-muted-foreground">
              {t('downloadEvents.totalRecords', { total: data.total, page: page + 1 })}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                {t('downloadEvents.prevPage')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(page + 1) * 20 >= data.total}
                onClick={() => setPage(page + 1)}
              >
                {t('downloadEvents.nextPage')}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

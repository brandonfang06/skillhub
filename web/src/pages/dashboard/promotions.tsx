import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useApprovePromotion, usePromotionList, useRejectPromotion } from '@/features/promotion/use-promotion-list'
import { DashboardPageHeader } from '@/shared/components/dashboard-page-header'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { formatCompactCount } from '@/shared/lib/number-format'
import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import type { PromotionTask } from '@/api/types'
import type { PromotionSortDirection, PromotionStatus } from '@/features/promotion/use-promotion-list'

type HistoryPromotionStatus = Extract<PromotionStatus, 'APPROVED' | 'REJECTED'>

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`
}

function formatUserName(displayName: string | null | undefined, userId: string | null | undefined, fallback: string) {
  return displayName || userId || fallback
}

function sourceCoordinate(item: PromotionTask) {
  return `@${item.sourceNamespace}/${item.sourceSkillSlug}`
}

function promotionCoordinate(item: PromotionTask) {
  return `${sourceCoordinate(item)} -> @${item.targetNamespace}`
}

function SorterGlyph({ direction }: { direction: PromotionSortDirection }) {
  return (
    <span aria-hidden="true" className="flex h-4 w-3 flex-col items-center justify-center gap-0.5">
      <span
        className={cn(
          'h-0 w-0 border-x-[4px] border-b-[5px] border-x-transparent',
          direction === 'ASC' ? 'border-b-foreground' : 'border-b-muted-foreground/45'
        )}
      />
      <span
        className={cn(
          'h-0 w-0 border-x-[4px] border-t-[5px] border-x-transparent',
          direction === 'DESC' ? 'border-t-foreground' : 'border-t-muted-foreground/45'
        )}
      />
    </span>
  )
}

function PendingPromotionCard({
  item,
  comment,
  isMutating,
  onCommentChange,
  onApprove,
  onReject,
}: {
  item: PromotionTask
  comment: string
  isMutating: boolean
  onCommentChange: (value: string) => void
  onApprove: () => void
  onReject: () => void
}) {
  const { t, i18n } = useTranslation()
  const submitter = formatUserName(item.submittedByName, item.submittedBy, t('promotions.emptyValue'))
  return (
    <Card className="space-y-4 p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-1">
          <h3 className="break-words font-heading text-base font-semibold text-foreground">{item.sourceSkillDisplayName}</h3>
          <p className="break-words text-sm text-muted-foreground [overflow-wrap:anywhere]">{promotionCoordinate(item)}</p>
        </div>
        <div className="shrink-0 text-sm text-muted-foreground">{formatLocalDateTime(item.submittedAt, i18n.language)}</div>
      </div>
      {item.sourceSkillSummary ? (
        <p className="text-sm leading-6 text-muted-foreground break-words [overflow-wrap:anywhere] line-clamp-2">
          {item.sourceSkillSummary}
        </p>
      ) : null}
      <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2 lg:grid-cols-3">
        <span>{t('promotions.versionTag', { version: item.sourceVersion })}</span>
        <span>{t('promotions.submitterTag', { user: submitter })}</span>
        <span>{t('promotions.fileCountTag', { count: item.sourceVersionFileCount })}</span>
        <span>{t('promotions.packageSizeTag', { size: formatFileSize(item.sourceVersionTotalSize) })}</span>
        <span>{t('promotions.downloadCountTag', { value: formatCompactCount(item.sourceSkillDownloadCount) })}</span>
        <span>{t('promotions.starCountTag', { value: formatCompactCount(item.sourceSkillStarCount) })}</span>
      </div>
      <Input
        placeholder={t('promotions.commentPlaceholder')}
        value={comment}
        onChange={(event) => onCommentChange(event.target.value)}
      />
      <div className="flex flex-wrap gap-3">
        <Button onClick={onApprove} disabled={isMutating}>
          {t('promotions.approve')}
        </Button>
        <Button variant="destructive" onClick={onReject} disabled={isMutating}>
          {t('promotions.reject')}
        </Button>
      </div>
    </Card>
  )
}

function PendingPromotionList() {
  const { t } = useTranslation()
  const { data: items, isLoading } = usePromotionList({ status: 'PENDING' })
  const approveMutation = useApprovePromotion()
  const rejectMutation = useRejectPromotion()
  const [commentById, setCommentById] = useState<Record<number, string>>({})

  if (isLoading) {
    return <div className="h-32 animate-shimmer rounded-xl" />
  }

  if (!items || items.length === 0) {
    return <div className="rounded-xl border border-dashed border-border/70 p-10 text-center text-muted-foreground">{t('promotions.empty')}</div>
  }

  const isMutating = approveMutation.isPending || rejectMutation.isPending
  return (
    <div className="space-y-4">
      {items.map((item) => (
        <PendingPromotionCard
          key={item.id}
          item={item}
          comment={commentById[item.id] ?? ''}
          isMutating={isMutating}
          onCommentChange={(value) => setCommentById((prev) => ({ ...prev, [item.id]: value }))}
          onApprove={() => approveMutation.mutate({ id: item.id, comment: commentById[item.id] })}
          onReject={() => rejectMutation.mutate({ id: item.id, comment: commentById[item.id] })}
        />
      ))}
    </div>
  )
}

function PromotionHistoryTable({
  status,
  sortDirection,
  onToggleSort,
}: {
  status: HistoryPromotionStatus
  sortDirection: PromotionSortDirection
  onToggleSort: () => void
}) {
  const { t, i18n } = useTranslation()
  const { data: items, isLoading } = usePromotionList({ status, sortBy: 'reviewedAt', sortDirection })
  const nextDirection = sortDirection === 'DESC' ? 'ASC' : 'DESC'
  const sortLabel = nextDirection === 'ASC' ? t('promotions.sortReviewedTimeAsc') : t('promotions.sortReviewedTimeDesc')

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-16 animate-shimmer rounded-xl" />
        ))}
      </div>
    )
  }

  if (!items || items.length === 0) {
    return <div className="rounded-xl border border-dashed border-border/70 p-10 text-center text-muted-foreground">{t('promotions.empty')}</div>
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border/60">
      <Table aria-label={t('promotions.historyTableLabel')}>
        <TableHeader>
          <TableRow className="bg-muted/35">
            <TableHead className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{t('promotions.colSkill')}</TableHead>
            <TableHead className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{t('promotions.colVersion')}</TableHead>
            <TableHead className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{t('promotions.colSubmitter')}</TableHead>
            <TableHead className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{t('promotions.colReviewer')}</TableHead>
            <TableHead aria-sort={sortDirection === 'DESC' ? 'descending' : 'ascending'} className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 gap-2 px-0 text-xs uppercase tracking-[0.18em] text-muted-foreground hover:bg-transparent hover:text-foreground"
                aria-label={sortLabel}
                onClick={onToggleSort}
              >
                {t('promotions.colReviewedAt')}
                <SorterGlyph direction={sortDirection} />
              </Button>
            </TableHead>
            <TableHead className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{t('promotions.colReviewComment')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => {
            const reviewCommentId = `promotion-review-comment-${item.id}`
            return (
              <TableRow key={item.id}>
                <TableCell>
                  <div className="min-w-0">
                    <div className="break-words font-medium text-foreground">{item.sourceSkillDisplayName}</div>
                    <div className="break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">{sourceCoordinate(item)}</div>
                  </div>
                </TableCell>
                <TableCell>{t('promotions.versionTag', { version: item.sourceVersion })}</TableCell>
                <TableCell>{formatUserName(item.submittedByName, item.submittedBy, t('promotions.emptyValue'))}</TableCell>
                <TableCell>{formatUserName(item.reviewedByName, item.reviewedBy, t('promotions.emptyValue'))}</TableCell>
                <TableCell>{item.reviewedAt ? formatLocalDateTime(item.reviewedAt, i18n.language) : t('promotions.emptyValue')}</TableCell>
                <TableCell className="max-w-[18rem]">
                  {item.reviewComment ? (
                    <>
                      <p id={`${reviewCommentId}-visible`} aria-describedby={reviewCommentId} className="line-clamp-2 break-words text-sm text-muted-foreground [overflow-wrap:anywhere]">
                        {item.reviewComment}
                      </p>
                      <span id={reviewCommentId} className="sr-only">{item.reviewComment}</span>
                    </>
                  ) : (
                    t('promotions.emptyValue')
                  )}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

/**
 * Dashboard page for namespace promotion requests.
 */
export function PromotionsPage() {
  const { t } = useTranslation()
  const [historySortDirection, setHistorySortDirection] = useState<Record<HistoryPromotionStatus, PromotionSortDirection>>({
    APPROVED: 'DESC',
    REJECTED: 'DESC',
  })

  function toggleHistorySort(status: HistoryPromotionStatus) {
    setHistorySortDirection((current) => ({
      ...current,
      [status]: current[status] === 'DESC' ? 'ASC' : 'DESC',
    }))
  }

  return (
    <div className="space-y-8 animate-fade-up">
      <DashboardPageHeader title={t('promotions.title')} subtitle={t('promotions.subtitle')} />
      <Tabs defaultValue="PENDING">
        <TabsList>
          <TabsTrigger value="PENDING">{t('promotions.tabPending')}</TabsTrigger>
          <TabsTrigger value="APPROVED">{t('promotions.tabApproved')}</TabsTrigger>
          <TabsTrigger value="REJECTED">{t('promotions.tabRejected')}</TabsTrigger>
        </TabsList>
        <TabsContent value="PENDING" className="mt-6">
          <PendingPromotionList />
        </TabsContent>
        <TabsContent value="APPROVED" className="mt-6">
          <PromotionHistoryTable
            status="APPROVED"
            sortDirection={historySortDirection.APPROVED}
            onToggleSort={() => toggleHistorySort('APPROVED')}
          />
        </TabsContent>
        <TabsContent value="REJECTED" className="mt-6">
          <PromotionHistoryTable
            status="REJECTED"
            sortDirection={historySortDirection.REJECTED}
            onToggleSort={() => toggleHistorySort('REJECTED')}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}

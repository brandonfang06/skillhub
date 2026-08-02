import { useState } from 'react'
import { Link, useParams } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { buildNamespaceReviewDetailPath } from '@/features/review/review-paths'
import { useBatchReviewDecision } from '@/features/review/use-batch-review'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { toast } from '@/shared/lib/toast'
import { Card } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { Textarea } from '@/shared/ui/textarea'
import { useNamespaceDetail } from '@/shared/hooks/use-namespace-queries'
import { useReviewList } from '@/features/review/use-review-list'
import { DashboardPageHeader } from '@/shared/components/dashboard-page-header'
import { Pagination } from '@/shared/components/pagination'
import { NamespaceHeader } from '@/features/namespace/namespace-header'
import { ConfirmDialog } from '@/shared/components/confirm-dialog'

type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
type TimeSortDirection = 'ASC' | 'DESC'
const PAGE_SIZE = 10

export function toggleReviewSelection(selectedIds: number[], reviewTaskId: number, checked: boolean): number[] {
  if (checked) {
    return selectedIds.includes(reviewTaskId) ? selectedIds : [...selectedIds, reviewTaskId]
  }
  return selectedIds.filter((id) => id !== reviewTaskId)
}

export function toggleCurrentPageReviewSelection(
  selectedIds: number[],
  currentPageIds: number[],
  checked: boolean,
): number[] {
  if (checked) {
    return currentPageIds.reduce(
      (result, reviewTaskId) => toggleReviewSelection(result, reviewTaskId, true),
      selectedIds,
    )
  }
  const currentPageIdSet = new Set(currentPageIds)
  return selectedIds.filter((id) => !currentPageIdSet.has(id))
}

function ReviewListSection({
  namespaceId,
  slug,
  actionsDisabled = false,
}: {
  namespaceId?: number
  slug: string
  actionsDisabled?: boolean
}) {
  const { t, i18n } = useTranslation()
  const reviewsEnabled = typeof namespaceId === 'number' && namespaceId > 0
  const [pages, setPages] = useState<Record<ReviewStatus, number>>({
    PENDING: 0,
    APPROVED: 0,
    REJECTED: 0,
  })
  const [activeStatus, setActiveStatus] = useState<ReviewStatus>('PENDING')
  const [sortDirection, setSortDirection] = useState<TimeSortDirection>('DESC')
  const [selectedReviewIds, setSelectedReviewIds] = useState<number[]>([])
  const [approveDialogOpen, setApproveDialogOpen] = useState(false)
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false)
  const [rejectComment, setRejectComment] = useState('')
  const batchDecision = useBatchReviewDecision()
  const pending = useReviewList('PENDING', namespaceId, pages.PENDING, PAGE_SIZE, sortDirection, reviewsEnabled && activeStatus === 'PENDING')
  const approved = useReviewList('APPROVED', namespaceId, pages.APPROVED, PAGE_SIZE, sortDirection, reviewsEnabled && activeStatus === 'APPROVED')
  const rejected = useReviewList('REJECTED', namespaceId, pages.REJECTED, PAGE_SIZE, sortDirection, reviewsEnabled && activeStatus === 'REJECTED')

  const changePage = (status: ReviewStatus, nextPage: number) => {
    setSelectedReviewIds([])
    setPages((current) => ({ ...current, [status]: nextPage }))
  }

  const handleSortChange = (value: string) => {
    setSelectedReviewIds([])
    setSortDirection(value as TimeSortDirection)
    setPages({
      PENDING: 0,
      APPROVED: 0,
      REJECTED: 0,
    })
  }

  const handleStatusChange = (value: string) => {
    setSelectedReviewIds([])
    setApproveDialogOpen(false)
    setRejectDialogOpen(false)
    setRejectComment('')
    setActiveStatus(value as ReviewStatus)
  }

  const showBatchResult = (successCount: number, failureCount: number) => {
    if (failureCount === 0) {
      toast.success(t('nsReviews.batchSuccessTitle'), t('nsReviews.batchSuccessDescription', { count: successCount }))
      return
    }
    if (successCount > 0) {
      toast.warning(
        t('nsReviews.batchPartialTitle'),
        t('nsReviews.batchPartialDescription', { success: successCount, failure: failureCount }),
      )
      return
    }
    toast.error(t('nsReviews.batchFailedTitle'), t('nsReviews.batchFailedDescription', { count: failureCount }))
  }

  const submitBatchDecision = async (decision: 'APPROVE' | 'REJECT') => {
    if (selectedReviewIds.length === 0) {
      return
    }
    if (decision === 'REJECT' && !rejectComment.trim()) {
      toast.error(t('nsReviews.rejectReasonRequired'))
      return
    }

    try {
      const result = await batchDecision.mutateAsync({
        reviewTaskIds: selectedReviewIds,
        decision,
        comment: decision === 'REJECT' ? rejectComment.trim() : undefined,
      })
      setSelectedReviewIds([])
      setRejectComment('')
      showBatchResult(result.successCount, result.failureCount)
    } catch (error) {
      toast.error(t('nsReviews.batchRequestFailed'), error instanceof Error ? error.message : '')
      throw error
    }
  }

  const renderPagination = (status: ReviewStatus, totalElements: number, totalPages: number) => {
    if (totalPages <= 1) {
      return null
    }

    const currentPage = pages[status]

    return (
      <div className="flex flex-col gap-3 border-t border-border/60 px-5 py-4 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
        <p>{t('nsReviews.pageSummary', { total: totalElements, page: currentPage + 1 })}</p>
        <Pagination page={currentPage} totalPages={totalPages} onPageChange={(nextPage) => changePage(status, nextPage)} />
      </div>
    )
  }

  const renderItems = (query: typeof pending, status: ReviewStatus) => {
    if (query.isLoading) {
      return (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-16 animate-shimmer rounded-xl" />
          ))}
        </div>
      )
    }

    const list = query.data?.items
    if (!list || list.length === 0) {
      return <Card className="p-10 text-center text-muted-foreground">{t('nsReviews.empty')}</Card>
    }
    const currentPageIds = list.map((review) => review.id)
    const allCurrentPageSelected = currentPageIds.every((id) => selectedReviewIds.includes(id))
    return (
      <Card className="overflow-hidden divide-y divide-border/40">
        {status === 'PENDING' ? (
          <div className="flex flex-col gap-3 bg-secondary/30 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <label className="inline-flex min-h-8 items-center gap-3 text-sm font-medium text-foreground">
              <input
                type="checkbox"
                checked={allCurrentPageSelected}
                disabled={actionsDisabled || batchDecision.isPending}
                onChange={(event) => {
                  setSelectedReviewIds((current) =>
                    toggleCurrentPageReviewSelection(current, currentPageIds, event.target.checked),
                  )
                }}
                className="h-4 w-4 accent-primary"
              />
              {t('nsReviews.selectCurrentPage')}
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 text-sm text-muted-foreground">
                {t('nsReviews.selectedCount', { count: selectedReviewIds.length })}
              </span>
              <Button
                size="sm"
                disabled={actionsDisabled || batchDecision.isPending || selectedReviewIds.length === 0}
                onClick={() => setApproveDialogOpen(true)}
              >
                {t('nsReviews.approveSelected')}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={actionsDisabled || batchDecision.isPending || selectedReviewIds.length === 0}
                onClick={() => setRejectDialogOpen(true)}
              >
                {t('nsReviews.rejectSelected')}
              </Button>
            </div>
          </div>
        ) : null}
        {list.map((review) => (
          <div
            key={review.id}
            className="p-5"
            data-superseded-review={review.superseded ? 'true' : undefined}
          >
            <div className="flex items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                {status === 'PENDING' ? (
                  <input
                    type="checkbox"
                    aria-label={t('nsReviews.selectReview', { skill: `${review.namespace}/${review.skillSlug}` })}
                    data-testid={`review-select-${review.id}`}
                    checked={selectedReviewIds.includes(review.id)}
                    disabled={actionsDisabled || batchDecision.isPending}
                    onChange={(event) => {
                      setSelectedReviewIds((current) =>
                        toggleReviewSelection(current, review.id, event.target.checked),
                      )
                    }}
                    className="h-4 w-4 flex-none accent-primary"
                  />
                ) : null}
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-semibold font-heading">{review.namespace}/{review.skillSlug}</div>
                    {review.superseded ? (
                      <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-700 dark:text-amber-300">
                        {t('review.supersededBadge')}
                      </span>
                    ) : null}
                  </div>
                  <div className="text-sm text-muted-foreground">{t('nsReviews.version', { version: review.version })}</div>
                </div>
              </div>
              <div className="text-sm text-muted-foreground">
                {formatLocalDateTime(
                  status === 'PENDING' ? review.submittedAt : review.reviewedAt ?? review.submittedAt,
                  i18n.language,
                )}
              </div>
            </div>
            {review.reviewComment ? (
              <p className="mt-3 text-sm text-muted-foreground">{review.reviewComment}</p>
            ) : null}
            <div className="mt-4 flex justify-end">
              <Link
                to={buildNamespaceReviewDetailPath(slug, review.id)}
                className="inline-flex items-center rounded-md border border-border/60 px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                {t('nsReviews.openReview')}
              </Link>
            </div>
          </div>
        ))}
        {query.data ? renderPagination(status, query.data.totalElements, query.data.totalPages) : null}
        <ConfirmDialog
          open={approveDialogOpen}
          onOpenChange={setApproveDialogOpen}
          title={t('nsReviews.approveDialogTitle')}
          description={t('nsReviews.approveDialogDescription', { count: selectedReviewIds.length })}
          confirmText={t('nsReviews.approveSelected')}
          onConfirm={() => submitBatchDecision('APPROVE')}
        />
        <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('nsReviews.rejectDialogTitle')}</DialogTitle>
              <DialogDescription>
                {t('nsReviews.rejectDialogDescription', { count: selectedReviewIds.length })}
              </DialogDescription>
            </DialogHeader>
            <Textarea
              value={rejectComment}
              onChange={(event) => setRejectComment(event.target.value)}
              placeholder={t('nsReviews.rejectReasonPlaceholder')}
              disabled={batchDecision.isPending}
            />
            {!rejectComment.trim() ? (
              <p className="text-sm text-destructive">{t('nsReviews.rejectReasonRequired')}</p>
            ) : null}
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectDialogOpen(false)} disabled={batchDecision.isPending}>
                {t('dialog.cancel')}
              </Button>
              <Button
                variant="destructive"
                disabled={batchDecision.isPending || !rejectComment.trim()}
                onClick={() => {
                  void submitBatchDecision('REJECT')
                    .then(() => setRejectDialogOpen(false))
                    .catch(() => undefined)
                }}
              >
                {t('nsReviews.rejectSelected')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </Card>
    )
  }

  return (
    <Tabs value={activeStatus} onValueChange={handleStatusChange}>
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <TabsList>
          <TabsTrigger value="PENDING">{t('nsReviews.tabPending')}</TabsTrigger>
          <TabsTrigger value="APPROVED">{t('nsReviews.tabApproved')}</TabsTrigger>
          <TabsTrigger value="REJECTED">{t('nsReviews.tabRejected')}</TabsTrigger>
        </TabsList>
        <div className="w-full max-w-48">
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {t('nsReviews.sortLabel')}
          </p>
          <Select value={sortDirection} onValueChange={handleSortChange}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="DESC">{t('nsReviews.sortNewest')}</SelectItem>
              <SelectItem value="ASC">{t('nsReviews.sortOldest')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <TabsContent value="PENDING" className="mt-0">{renderItems(pending, 'PENDING')}</TabsContent>
      <TabsContent value="APPROVED" className="mt-0">{renderItems(approved, 'APPROVED')}</TabsContent>
      <TabsContent value="REJECTED" className="mt-0">{renderItems(rejected, 'REJECTED')}</TabsContent>
    </Tabs>
  )
}

export function NamespaceReviewsPage() {
  const { t } = useTranslation()
  const { slug } = useParams({ from: '/dashboard/namespaces/$slug/reviews' })
  const { data: namespace } = useNamespaceDetail(slug)
  const readOnlyMessage = namespace?.type === 'GLOBAL'
    ? t('nsReviews.globalReadOnly')
    : namespace?.status === 'FROZEN'
      ? t('nsReviews.frozenReadOnly')
      : namespace?.status === 'ARCHIVED'
        ? t('nsReviews.archivedReadOnly')
        : null

  return (
    <div className="space-y-8 animate-fade-up">
      <DashboardPageHeader
        title={t('nsReviews.title')}
        subtitle={namespace ? t('nsReviews.reviewsFor', { name: namespace.displayName }) : t('nsReviews.loadingNamespace')}
      />
      {namespace ? <NamespaceHeader namespace={namespace} /> : null}
      {readOnlyMessage ? (
        <Card className="border-border/50 bg-secondary/40 p-4 text-sm text-muted-foreground">
          {readOnlyMessage}
        </Card>
      ) : null}
      <ReviewListSection namespaceId={namespace?.id} slug={slug} actionsDisabled={Boolean(readOnlyMessage)} />
    </div>
  )
}

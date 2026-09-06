import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { ChevronDown, ChevronUp, Clock3, RotateCcw, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ReviewProgress } from '@/api/types'
import { ReviewAttemptTimeline } from '@/features/review/review-attempt-timeline'
import { useMyReviewAttempts, useMyReviewProgress } from '@/features/review/use-my-review-progress'
import { DashboardPageHeader } from '@/shared/components/dashboard-page-header'
import { Pagination } from '@/shared/components/pagination'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { cn } from '@/shared/lib/utils'
import { Button, buttonVariants } from '@/shared/ui/button'
import { Card, CardContent } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'

type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
const PAGE_SIZE = 20
const statusClasses: Record<ReviewStatus, string> = {
  PENDING: 'border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-300',
  APPROVED: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300',
  REJECTED: 'border-red-500/25 bg-red-500/10 text-red-800 dark:text-red-300',
}

export function ReviewProgressPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const search = useSearch({ from: '/dashboard/review-progress' })
  const [queryInput, setQueryInput] = useState(search.q ?? '')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const page = search.page ?? 0
  const query = useMyReviewProgress({ status: search.status, q: search.q, page, size: PAGE_SIZE })
  const totalPages = query.data ? Math.ceil(query.data.total / query.data.size) : 0

  function updateSearch(next: { status?: ReviewStatus | null; q?: string; page?: number }) {
    void navigate({ to: '/dashboard/review-progress', search: { status: next.status === null ? undefined : next.status ?? search.status, q: next.q ?? search.q, page: next.page ?? 0 }, replace: true })
  }

  function submitSearch(event: FormEvent) { event.preventDefault(); updateSearch({ q: queryInput.trim(), page: 0 }) }

  return <div className="space-y-8 animate-fade-up">
    <DashboardPageHeader title={t('reviewProgress.title')} subtitle={t('reviewProgress.subtitle')} />
    <Card><CardContent className="space-y-6 p-5 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row"><form className="flex flex-1 gap-2" onSubmit={submitSearch}><div className="relative flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" /><Input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} aria-label={t('reviewProgress.searchLabel')} className="pl-9" /></div><Button type="submit" variant="outline">{t('reviewProgress.searchAction')}</Button></form><Select value={search.status ?? 'ALL'} onValueChange={(value) => updateSearch({ status: value === 'ALL' ? null : value as ReviewStatus })}><SelectTrigger className="md:w-48" aria-label={t('reviewProgress.statusFilter')}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="ALL">{t('reviewProgress.statusAll')}</SelectItem><SelectItem value="PENDING">{t('reviewProgress.statusPending')}</SelectItem><SelectItem value="APPROVED">{t('reviewProgress.statusApproved')}</SelectItem><SelectItem value="REJECTED">{t('reviewProgress.statusRejected')}</SelectItem></SelectContent></Select></div>
      {query.data ? <div aria-label={t('reviewProgress.statusSummary')} className="grid gap-3 sm:grid-cols-3">{(['PENDING', 'APPROVED', 'REJECTED'] as const).map((status) => <button key={status} type="button" onClick={() => updateSearch({ status })} className="rounded-xl border p-3 text-left"><strong className="block text-2xl">{query.data!.statusCounts[status.toLowerCase() as 'pending' | 'approved' | 'rejected']}</strong>{t(`reviewProgress.status${status === 'PENDING' ? 'Pending' : status === 'APPROVED' ? 'Approved' : 'Rejected'}`)}</button>)}</div> : null}
      {query.isLoading ? <div className="h-28 animate-shimmer rounded-xl" /> : query.isError ? <p className="text-destructive">{t('reviewProgress.error')}</p> : query.data?.items.length ? <div className="space-y-3">{query.data.items.map((item) => <ProgressItem key={`${item.skillId}:${item.skillVersion}`} item={item} expanded={expandedId === item.latestReviewTaskId} onToggle={() => setExpandedId(expandedId === item.latestReviewTaskId ? null : item.latestReviewTaskId)} locale={i18n.language} />)}</div> : <div className="py-14 text-center"><Clock3 className="mx-auto h-8 w-8" /><p>{t('reviewProgress.emptyTitle')}</p></div>}
      {totalPages > 1 ? <Pagination page={page} totalPages={totalPages} onPageChange={(nextPage) => updateSearch({ page: nextPage })} /> : null}
    </CardContent></Card>
  </div>
}

function ProgressItem({ item, expanded, onToggle, locale }: { item: ReviewProgress; expanded: boolean; onToggle: () => void; locale: string }) {
  const { t } = useTranslation()
  const attempts = useMyReviewAttempts(expanded ? item.latestReviewTaskId : null)
  const suffix = item.latestStatus === 'PENDING' ? 'Pending' : item.latestStatus === 'APPROVED' ? 'Approved' : 'Rejected'
  return <article className="rounded-xl border"><div className="flex flex-col gap-4 p-4 md:flex-row md:justify-between"><div><div className="flex flex-wrap gap-2"><Link to="/space/$namespace/$slug" params={{ namespace: item.namespace, slug: item.skillSlug }} className="font-semibold">@{item.namespace}/{item.skillSlug}</Link><span>v{item.skillVersion}</span><span className={cn('rounded-full border px-2', statusClasses[item.latestStatus])}>{t(`reviewProgress.status${suffix}`)}</span></div><p className="text-sm text-muted-foreground">{t('reviewProgress.latestSubmitted', { time: formatLocalDateTime(item.latestSubmittedAt, locale) })} · {t('reviewProgress.attemptCount', { count: item.attemptCount })}</p>{item.latestReviewComment ? <p>{item.latestReviewComment}</p> : null}</div><div className="flex gap-2">{item.latestStatus === 'REJECTED' ? <Link to="/dashboard/publish" search={{ namespace: item.namespace, resubmitSkill: item.skillSlug, resubmitVersion: item.skillVersion }} className={buttonVariants({ variant: 'outline', size: 'sm' })}><RotateCcw className="h-4 w-4" />{t('reviewProgress.resubmit')}</Link> : null}<Button type="button" variant="ghost" size="sm" onClick={onToggle}>{t('reviewProgress.history')}{expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</Button></div></div>{expanded ? <div className="border-t p-4">{attempts.isLoading ? <div className="h-16 animate-shimmer" /> : attempts.isError ? <p>{t('reviewProgress.historyError')}</p> : <ReviewAttemptTimeline attempts={attempts.data ?? []} locale={locale} />}</div> : null}</article>
}

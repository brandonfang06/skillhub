import { useId, useState } from 'react'
import { ChevronDown, ChevronUp, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/features/auth/use-auth'
import { formatLocalDateTime, parseServerDateTime } from '@/shared/lib/date-time'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { useReviewContext, type VersionReviewContext } from './use-review-context'

export function NamespaceReviewersCard({ skillId, version, defaultExpanded = true }: {
  skillId: number; version: string; defaultExpanded?: boolean
}) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [page, setPage] = useState(0)
  const contentId = useId()
  const query = useReviewContext(skillId, version, user?.userId, page, expanded)
  if (!user) return null

  return <Card className="min-w-0 overflow-hidden">
    <button type="button" className="flex w-full items-center gap-3 p-4 text-left hover:bg-muted/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary" aria-expanded={expanded} aria-controls={contentId} onClick={() => setExpanded(!expanded)}>
      <Users className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
      <span className="min-w-0 flex-1"><span className="block font-semibold">{t('namespaceReviewers.title')}</span><span className="block break-all text-sm text-muted-foreground">{t('namespaceReviewers.version', { version })}</span></span>
      {expanded ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
    </button>
    {expanded ? <div id={contentId} className="border-t p-4" aria-live="polite">
      {query.isPending ? <p role="status">{t('namespaceReviewers.loading')}</p> : query.isError ? <div role="alert"><p>{t('namespaceReviewers.error')}</p><Button variant="outline" className="mt-2" onClick={() => void query.refetch()}>{t('namespaceReviewers.retry')}</Button></div> : <NamespaceReviewContextContent data={query.data} onPageChange={setPage} />}
    </div> : null}
  </Card>
}

export function NamespaceReviewContextContent({ data, onPageChange }: { data: VersionReviewContext; onPageChange: (page: number) => void }) {
  const { t, i18n } = useTranslation()
  const complete = data.waitingReason === 'APPROVED' || data.waitingReason === 'REJECTED'
  const showPeople = !complete && data.waitingReason !== 'NOT_SUBMITTED'
  const waitingMinutes = data.submittedAt ? Math.max(0, Math.floor((Date.now() - parseServerDateTime(data.submittedAt).getTime()) / 60_000)) : 0

  return <div className="space-y-3 text-sm">
    <p className="font-medium">{t(`namespaceReviewers.reasons.${data.waitingReason}`)}</p>
    {data.submittedAt ? <p className="text-muted-foreground">{t('namespaceReviewers.submitted', { time: formatLocalDateTime(data.submittedAt, i18n.language) })}{showPeople ? ` · ${t('namespaceReviewers.waiting', { count: waitingMinutes })}` : ''}</p> : null}
    {complete ? <div><p>{t('namespaceReviewers.reviewed', { name: data.reviewedByName || t('namespaceReviewers.unknownReviewer'), time: formatLocalDateTime(data.reviewedAt, i18n.language) })}</p>{data.reviewComment ? <p className="mt-2 whitespace-pre-wrap break-words">{data.reviewComment}</p> : null}</div> : showPeople ? data.namespaceType === 'GLOBAL' ? <p>{t('namespaceReviewers.global')}</p> : <>
      {data.waitingReason === 'HUMAN_REVIEW' ? <p className="text-muted-foreground">{t('namespaceReviewers.anyOne')}</p> : <p className="text-muted-foreground">{t('namespaceReviewers.blocked')}</p>}
      <p className="font-medium">{t('namespaceReviewers.total', { count: data.total })}</p>
      {data.total === 0 ? <p>{t('namespaceReviewers.empty')}</p> : <ul className="grid gap-2 sm:grid-cols-2">{data.reviewers.map((person) => <li key={person.userId} className="min-w-0 rounded-lg border bg-muted/30 px-3 py-2"><span className="block break-words font-medium">{person.displayName}</span>{person.loginName && person.loginName !== person.displayName ? <span className="block break-all text-muted-foreground">{person.loginName}</span> : null}</li>)}</ul>}
      {data.total > data.size || data.page > 0 ? <div className="flex flex-wrap items-center justify-between gap-2"><Button type="button" variant="outline" size="sm" disabled={data.page === 0} onClick={() => onPageChange(data.page - 1)}>{t('namespaceReviewers.previous')}</Button><span>{t('namespaceReviewers.page', { page: data.page + 1, total: Math.max(1, Math.ceil(data.total / data.size)) })}</span><Button type="button" variant="outline" size="sm" disabled={(data.page + 1) * data.size >= data.total} onClick={() => onPageChange(data.page + 1)}>{t('namespaceReviewers.next')}</Button></div> : null}
      <p className="text-xs text-muted-foreground">{t('namespaceReviewers.authorityNote')}</p>
    </> : null}
  </div>
}

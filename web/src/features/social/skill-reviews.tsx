import { useId, useState } from 'react'
import { Loader2, MessageSquare, ShieldAlert, Star } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/features/auth/use-auth'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { Textarea } from '@/shared/ui/textarea'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { toast } from '@/shared/lib/toast'
import { cn } from '@/shared/lib/utils'
import { type MySkillReview, type SkillReview, useClearSkillReview, useModerateSkillReview, useMySkillReview, useSkillReviews, useUpsertSkillReview } from './use-skill-reviews'

function Stars({ value, onChange, disabled }: { value: number; onChange?: (score: number) => void; disabled?: boolean }) {
  const { t } = useTranslation()
  const name = useId()
  if (!onChange) return <div className="flex gap-1" role="img" aria-label={t('skillReviews.ratingDisplay', { score: value })}>{[1, 2, 3, 4, 5].map((score) => <Star key={score} className={cn('h-4 w-4', score <= value && 'fill-yellow-400 text-yellow-400')} />)}</div>
  return <div className="flex gap-1" role="radiogroup" aria-label={t('skillReviews.scoreLabel')}>{[1, 2, 3, 4, 5].map((score) => <span key={score}><input id={`${name}-${score}`} className="sr-only" type="radio" name={name} checked={score === value} onChange={() => onChange(score)} disabled={disabled} aria-label={t('skillReviews.ratingOption', { score })} /><label htmlFor={`${name}-${score}`}><Star className={cn('h-4 w-4 cursor-pointer', score <= value && 'fill-yellow-400 text-yellow-400')} /></label></span>)}</div>
}

function Editor({ skillId, review, onDone }: { skillId: number; review?: MySkillReview; onDone: () => void }) {
  const { t } = useTranslation()
  const textId = useId()
  const [score, setScore] = useState(review?.rated ? review.score : 5)
  const [reviewText, setReviewText] = useState(review?.reviewText ?? '')
  const save = useUpsertSkillReview(skillId)
  const clear = useClearSkillReview(skillId)
  const pending = save.isPending || clear.isPending
  const handleSave = () => save.mutate({ score, reviewText: reviewText.trim(), lockVersion: review?.lockVersion ?? 0 }, { onSuccess: () => { toast.success(t('skillReviews.saved')); onDone() }, onError: (error) => toast.error(t('skillReviews.saveFailed'), error.message) })
  const handleDelete = () => clear.mutate(review?.lockVersion ?? 0, { onSuccess: () => { toast.success(t('skillReviews.deleted')); onDone() }, onError: (error) => toast.error(t('skillReviews.deleteFailed'), error.message) })
  return <div className="space-y-4 rounded-xl border p-4"><Stars value={score} onChange={setScore} disabled={pending} /><label htmlFor={textId} className="sr-only">{t('skillReviews.reviewTextLabel')}</label><Textarea id={textId} value={reviewText} onChange={(event) => setReviewText(event.target.value)} maxLength={2000} disabled={pending} /><div className="flex justify-end gap-2">{review?.reviewed ? <Button variant="ghost" size="sm" onClick={handleDelete}>{t('skillReviews.delete')}</Button> : null}<Button variant="outline" size="sm" onClick={onDone}>{t('skillReviews.cancel')}</Button><Button size="sm" onClick={handleSave} disabled={pending || !reviewText.trim()}>{t('skillReviews.save')}</Button></div></div>
}

function Row({ skillId, review, canModerate }: { skillId: number; review: SkillReview; canModerate: boolean }) {
  const { t, i18n } = useTranslation()
  const mutation = useModerateSkillReview(skillId)
  const hidden = review.status === 'HIDDEN'
  const moderate = () => mutation.mutate({ reviewId: review.id, action: hidden ? 'restore' : 'hide' })
  return <div className={cn('space-y-3 py-5', hidden && 'opacity-60')}><div className="flex justify-between gap-3"><div><div className="flex gap-2"><strong className="break-words [overflow-wrap:anywhere]">{review.displayName}</strong><Stars value={review.score} />{hidden ? <span>{t('skillReviews.hiddenStatus')}</span> : null}</div><p className="mt-2 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{review.reviewText}</p>{review.moderationReason ? <p className="text-xs text-muted-foreground">{t('skillReviews.moderationReason', { reason: review.moderationReason })}</p> : null}</div><time className="text-xs" dateTime={review.updatedAt}>{formatLocalDateTime(review.updatedAt, i18n.language)}</time></div>{canModerate ? <div className="flex justify-end"><Button variant="ghost" size="sm" onClick={moderate}><ShieldAlert className="mr-2 h-4 w-4" />{t(hidden ? 'skillReviews.restore' : 'skillReviews.hide')}</Button></div> : null}</div>
}

export function SkillReviews({ skillId, canInteract, onRequireLogin }: { skillId: number; canInteract: boolean; onRequireLogin: () => void }) {
  const { t } = useTranslation()
  const { isAuthenticated, hasRole } = useAuth()
  const [page, setPage] = useState(0)
  const [editing, setEditing] = useState(false)
  const reviews = useSkillReviews(skillId, page)
  const mine = useMySkillReview(skillId, isAuthenticated)
  const clear = useClearSkillReview(skillId)
  const canModerate = hasRole('SKILL_ADMIN') || hasRole('SUPER_ADMIN')
  const start = () => isAuthenticated ? setEditing(true) : onRequireLogin()
  return <Card className="space-y-5 p-6"><div className="flex justify-between"><div><h2 className="flex gap-2 font-semibold"><MessageSquare className="h-5 w-5" />{t('skillReviews.title')}</h2><p>{t('skillReviews.count', { count: reviews.data?.total ?? 0 })}</p></div>{canInteract && !editing ? <Button variant="outline" onClick={start}>{t(mine.data?.reviewed ? 'skillReviews.edit' : 'skillReviews.write')}</Button> : !canInteract && isAuthenticated && mine.data?.reviewed ? <Button variant="outline" onClick={() => clear.mutate(mine.data!.lockVersion)}>{t('skillReviews.delete')}</Button> : null}</div>{mine.data?.status === 'HIDDEN' ? <div className="rounded-xl border p-3 text-sm">{t('skillReviews.yourReviewHidden')}{mine.data.moderationReason ? ` ${t('skillReviews.moderationReason', { reason: mine.data.moderationReason })}` : ''}</div> : null}{editing ? <Editor skillId={skillId} review={mine.data} onDone={() => { setEditing(false); setPage(0) }} /> : null}{reviews.isLoading ? <div><Loader2 className="animate-spin" />{t('skillReviews.loading')}</div> : reviews.isError ? <p>{t('skillReviews.loadFailed')}</p> : reviews.data?.items.length ? <div className="divide-y">{reviews.data.items.map((review) => <Row key={review.id} skillId={skillId} review={review} canModerate={canModerate} />)}</div> : <p className="py-10 text-center">{t('skillReviews.empty')}</p>}{page > 0 || (reviews.data && reviews.data.total > reviews.data.size) ? <div className="flex justify-end gap-2"><Button disabled={page === 0} onClick={() => setPage(page - 1)}>{t('skillReviews.previous')}</Button><Button disabled={!reviews.data || (page + 1) * reviews.data.size >= reviews.data.total} onClick={() => setPage(page + 1)}>{t('skillReviews.next')}</Button></div> : null}</Card>
}

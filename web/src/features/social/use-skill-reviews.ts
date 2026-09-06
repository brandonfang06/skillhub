import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson, getCsrfHeaders, WEB_API_PREFIX } from '@/api/client'

export interface SkillReview {
  id: number
  displayName: string
  avatarUrl?: string | null
  score: number
  reviewText: string
  status: 'VISIBLE' | 'HIDDEN'
  authoredByViewer: boolean
  moderationReason?: string | null
  createdAt: string
  updatedAt: string
  lockVersion: number
}

export interface MySkillReview {
  rated: boolean
  score: number
  reviewed: boolean
  reviewId?: number
  reviewText?: string | null
  status?: 'VISIBLE' | 'HIDDEN'
  moderationReason?: string | null
  updatedAt?: string
  lockVersion: number
}

interface SkillReviewPage { items: SkillReview[]; total: number; page: number; size: number }
interface ReviewInput { score: number; reviewText: string; lockVersion: number }

export function useSkillReviews(skillId: number, page: number) {
  return useQuery({ queryKey: ['skills', skillId, 'reviews', page], queryFn: () => fetchJson<SkillReviewPage>(`${WEB_API_PREFIX}/skills/${skillId}/reviews?page=${page}&size=20`), enabled: skillId > 0 })
}

export function useMySkillReview(skillId: number, enabled: boolean) {
  return useQuery({ queryKey: ['skills', skillId, 'reviews', 'me'], queryFn: () => fetchJson<MySkillReview>(`${WEB_API_PREFIX}/skills/${skillId}/reviews/me`), enabled: enabled && skillId > 0 })
}

function useInvalidation(skillId: number) {
  const client = useQueryClient()
  return () => {
    client.invalidateQueries({ queryKey: ['skills', skillId, 'reviews'] })
    client.invalidateQueries({ queryKey: ['skills', skillId, 'rating'] })
    client.invalidateQueries({ queryKey: ['skills'] })
  }
}

export function useUpsertSkillReview(skillId: number) {
  const onSuccess = useInvalidation(skillId)
  return useMutation({ mutationFn: (input: ReviewInput) => fetchJson<MySkillReview>(`${WEB_API_PREFIX}/skills/${skillId}/reviews/me`, { method: 'PUT', headers: getCsrfHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(input) }), onSuccess })
}

export function useClearSkillReview(skillId: number) {
  const onSuccess = useInvalidation(skillId)
  return useMutation({ mutationFn: (lockVersion: number) => fetchJson<MySkillReview>(`${WEB_API_PREFIX}/skills/${skillId}/reviews/me?lockVersion=${lockVersion}`, { method: 'DELETE', headers: getCsrfHeaders() }), onSuccess })
}

export function useModerateSkillReview(skillId: number) {
  const onSuccess = useInvalidation(skillId)
  return useMutation({ mutationFn: ({ reviewId, action, reason }: { reviewId: number; action: 'hide' | 'restore'; reason?: string }) => fetchJson<SkillReview>(`/api/v1/admin/skill-reviews/${reviewId}/${action}`, { method: 'POST', headers: getCsrfHeaders({ 'Content-Type': 'application/json' }), body: action === 'hide' ? JSON.stringify({ reason }) : undefined }), onSuccess })
}

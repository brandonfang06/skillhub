import { useQuery } from '@tanstack/react-query'
import { reviewApi } from '@/api/client'

export function useMyReviewProgress(params: { status?: string; q?: string; page: number; size: number }) {
  return useQuery({ queryKey: ['reviews', 'my-progress', params], queryFn: () => reviewApi.listMyProgress(params) })
}

export function useMyReviewAttempts(reviewTaskId: number | null) {
  return useQuery({
    queryKey: ['reviews', 'my-progress', reviewTaskId, 'attempts'],
    queryFn: () => reviewApi.listMyAttempts(reviewTaskId!),
    enabled: reviewTaskId !== null,
  })
}

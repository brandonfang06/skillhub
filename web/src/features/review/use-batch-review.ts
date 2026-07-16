import { useMutation, useQueryClient } from '@tanstack/react-query'
import { reviewApi } from '@/api/client'
import type { ReviewBatchDecisionRequest, ReviewBatchDecisionResponse } from '@/api/types'

type BatchReviewCallbacks = {
  onSuccess?: (result: ReviewBatchDecisionResponse) => void
  onError?: (error: Error) => void
}

export function useBatchReviewDecision(callbacks?: BatchReviewCallbacks) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: ReviewBatchDecisionRequest) => reviewApi.batchDecision(request),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['reviews'] })
      queryClient.invalidateQueries({ queryKey: ['governance'] })
      queryClient.invalidateQueries({ queryKey: ['skills'] })
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      callbacks?.onSuccess?.(result)
    },
    onError: callbacks?.onError,
  })
}

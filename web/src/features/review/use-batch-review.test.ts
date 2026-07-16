import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  batchDecision: vi.fn(),
  invalidateQueries: vi.fn(),
  useMutation: vi.fn(),
}))

vi.mock('@tanstack/react-query', () => ({
  useMutation: mocks.useMutation,
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}))

vi.mock('@/api/client', () => ({
  reviewApi: {
    batchDecision: mocks.batchDecision,
  },
}))

import { useBatchReviewDecision } from './use-batch-review'

type MutationOptions = {
  mutationFn: (request: unknown) => Promise<unknown>
  onSuccess: (result: unknown) => void
}

function latestMutationOptions(): MutationOptions {
  const call = mocks.useMutation.mock.calls[mocks.useMutation.mock.calls.length - 1]
  if (!call) {
    throw new Error('useMutation was not called')
  }
  return call[0] as MutationOptions
}

describe('useBatchReviewDecision', () => {
  beforeEach(() => {
    mocks.batchDecision.mockReset()
    mocks.invalidateQueries.mockReset()
    mocks.useMutation.mockReset()
  })

  it('delegates one typed request to the review API', async () => {
    const request = {
      reviewTaskIds: [11, 12],
      decision: 'APPROVE' as const,
    }
    mocks.batchDecision.mockResolvedValue({
      totalCount: 2,
      successCount: 2,
      failureCount: 0,
      results: [],
    })

    useBatchReviewDecision()
    await latestMutationOptions().mutationFn(request)

    expect(mocks.batchDecision).toHaveBeenCalledOnce()
    expect(mocks.batchDecision).toHaveBeenCalledWith(request)
  })

  it('invalidates all review-related caches after a batch decision', () => {
    const onSuccess = vi.fn()

    useBatchReviewDecision({ onSuccess })
    latestMutationOptions().onSuccess({
      totalCount: 2,
      successCount: 1,
      failureCount: 1,
      results: [],
    })

    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['reviews'] })
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['governance'] })
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['skills'] })
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] })
    expect(onSuccess).toHaveBeenCalledOnce()
  })
})

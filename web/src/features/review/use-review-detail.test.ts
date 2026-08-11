import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  invalidateQueries: vi.fn(),
  useMutation: vi.fn(),
  useQuery: vi.fn(),
}))

vi.mock('@tanstack/react-query', () => ({
  useMutation: mocks.useMutation,
  useQuery: mocks.useQuery,
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}))

vi.mock('@/api/client', () => ({
  reviewApi: {
    approve: vi.fn(),
    get: vi.fn(),
    getSkillDetail: vi.fn(),
    reject: vi.fn(),
  },
}))

import { useApproveReview, useRejectReview, useReviewSkillDetail } from './use-review-detail'

type MutationOptions = {
  onSuccess: () => void
}

function latestMutationOptions(): MutationOptions {
  const call = mocks.useMutation.mock.calls[mocks.useMutation.mock.calls.length - 1]
  if (!call) {
    throw new Error('useMutation was not called')
  }
  return call[0] as MutationOptions
}

describe('use-review-detail mutations', () => {
  beforeEach(() => {
    mocks.invalidateQueries.mockReset()
    mocks.useMutation.mockReset()
    mocks.useQuery.mockReset()
  })

  it('invalidates review, governance, and skill caches after approval', () => {
    const onSuccess = vi.fn()

    useApproveReview({ onSuccess })
    latestMutationOptions().onSuccess()

    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['reviews'] })
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['governance'] })
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['skills'] })
    expect(onSuccess).toHaveBeenCalledOnce()
  })

  it('invalidates review, governance, and skill caches after rejection', () => {
    const onSuccess = vi.fn()

    useRejectReview({ onSuccess })
    latestMutationOptions().onSuccess()

    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['reviews'] })
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['governance'] })
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['skills'] })
    expect(onSuccess).toHaveBeenCalledOnce()
  })

  it('does not request artifact detail for an archived review', () => {
    useReviewSkillDetail(91, false)

    expect(mocks.useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['reviews', 91, 'skill-detail'],
        enabled: false,
      }),
    )
  })

  it('polls artifact detail while its active version is scanning', () => {
    useReviewSkillDetail(91)

    const options = mocks.useQuery.mock.calls[0]?.[0]
    expect(options.refetchInterval({
      state: { data: { versions: [{ status: 'SCANNING' }] } },
    })).toBe(3_000)
  })
})

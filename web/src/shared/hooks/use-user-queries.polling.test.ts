import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  useQuery: vi.fn(),
}))

vi.mock('@tanstack/react-query', () => ({
  keepPreviousData: Symbol('keepPreviousData'),
  useMutation: vi.fn(),
  useQuery: mocks.useQuery,
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/api/client', () => ({
  meApi: {},
  namespaceApi: {},
  promotionApi: {},
}))

import { useMySkills } from './use-user-queries'

describe('useMySkills scan polling', () => {
  beforeEach(() => {
    mocks.useQuery.mockReset()
  })

  it('polls while an owner preview version is scanning', () => {
    useMySkills()

    const options = mocks.useQuery.mock.calls[0]?.[0]
    expect(options.refetchInterval({
      state: {
        data: {
          items: [{ ownerPreviewVersion: { status: 'SCANNING' } }],
        },
      },
    })).toBe(3_000)
  })
})

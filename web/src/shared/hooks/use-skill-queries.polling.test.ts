import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  useQuery: vi.fn(),
}))

vi.mock('@tanstack/react-query', () => ({
  useMutation: vi.fn(),
  useQuery: mocks.useQuery,
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/api/client', () => ({
  WEB_API_PREFIX: '/api/v1',
  fetchJson: vi.fn(),
  fetchText: vi.fn(),
  getCsrfHeaders: vi.fn(),
  skillLifecycleApi: {},
}))

vi.mock('@/shared/hooks/use-auth', () => ({
  useAuth: () => ({ isLoading: false, user: null }),
}))

vi.mock('@/shared/lib/skill-navigation', () => ({}))

import { useSkillDetail, useSkillVersions } from './use-skill-queries'

describe('skill detail scan polling', () => {
  beforeEach(() => {
    mocks.useQuery.mockReset()
  })

  it('polls detail and version queries only while a version is scanning', () => {
    useSkillDetail('team', 'demo')
    useSkillVersions('team', 'demo')

    const detailOptions = mocks.useQuery.mock.calls[0]?.[0]
    const versionsOptions = mocks.useQuery.mock.calls[1]?.[0]

    expect(detailOptions.refetchInterval({
      state: { data: { headlineVersion: { status: 'SCANNING' } } },
    })).toBe(3_000)
    expect(versionsOptions.refetchInterval({
      state: { data: [{ status: 'SCAN_FAILED' }] },
    })).toBe(false)
  })
})

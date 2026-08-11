/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchJson: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  WEB_API_PREFIX: '/api/v1',
  fetchJson: mocks.fetchJson,
  fetchText: vi.fn(),
  getCsrfHeaders: vi.fn(),
  skillLifecycleApi: {},
}))

vi.mock('@/shared/hooks/use-auth', () => ({
  useAuth: () => ({ isLoading: false, user: { id: 'owner-1' } }),
}))

import { useSkillDetail } from './use-skill-queries'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useSkillDetail scan polling behavior', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('refreshes SCANNING to SCAN_FAILED and then stops polling', async () => {
    vi.useFakeTimers()
    mocks.fetchJson
      .mockResolvedValueOnce({
        headlineVersion: { id: 11, version: '1.0.0', status: 'SCANNING' },
      })
      .mockResolvedValue({
        headlineVersion: { id: 11, version: '1.0.0', status: 'SCAN_FAILED' },
      })

    const { result } = renderHook(
      () => useSkillDetail('team-ai', 'timeout-demo'),
      { wrapper: createWrapper() },
    )

    await act(async () => {
      await vi.waitFor(() => {
        expect(result.current.data?.headlineVersion?.status).toBe('SCANNING')
      })
    })
    expect(mocks.fetchJson).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000)
      await vi.waitFor(() => {
        expect(result.current.data?.headlineVersion?.status).toBe('SCAN_FAILED')
      })
    })
    expect(mocks.fetchJson).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000)
    })
    expect(mocks.fetchJson).toHaveBeenCalledTimes(2)
  })
})

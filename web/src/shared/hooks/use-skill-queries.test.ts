/** @vitest-environment jsdom */
import { createElement, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/i18n/config'
import { useSkillFile, useSkillReadme, useUpdateSkillVisibility } from './use-skill-queries'
import {
  getAdminLabelDefinitionsQueryKey,
  getSkillSearchQueryKey,
  getSkillDetailQueryKey,
  getSkillLabelsQueryKey,
  getVisibleLabelsQueryKey,
} from './query-keys'

const updateVisibilityMock = vi.hoisted(() => vi.fn())

function createQueryHarness() {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  })
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  return { queryClient, wrapper }
}

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    skillLifecycleApi: {
      ...actual.skillLifecycleApi,
      updateVisibility: updateVisibilityMock,
    },
  }
})

describe('localized label query keys', () => {
  const originalLanguage = i18n.language
  const originalResolvedLanguage = i18n.resolvedLanguage

  afterEach(() => {
    i18n.language = originalLanguage
    i18n.resolvedLanguage = originalResolvedLanguage
  })

  it('includes the current language so localized label data refetches after language switches', () => {
    i18n.language = 'en'
    i18n.resolvedLanguage = 'en'

    expect(getVisibleLabelsQueryKey()).toEqual(['labels', 'visible', 'en'])
    expect(getSkillSearchQueryKey({ q: 'agent', sort: 'newest' }, 'user-a')).toEqual([
      'skills',
      'search',
      'user-a',
      { q: 'agent', sort: 'newest' },
      'en',
    ])
    expect(getSkillLabelsQueryKey('team', 'demo')).toEqual(['labels', 'skill', 'team', 'demo', 'en'])
    expect(getSkillDetailQueryKey('team', 'demo')).toEqual(['skills', 'team', 'demo', 'en'])
    expect(getAdminLabelDefinitionsQueryKey()).toEqual(['labels', 'admin', 'en'])

    i18n.language = 'zh-CN'
    i18n.resolvedLanguage = 'zh-CN'

    expect(getVisibleLabelsQueryKey()).toEqual(['labels', 'visible', 'zh-CN'])
    expect(getSkillSearchQueryKey({ q: 'agent', sort: 'newest' }, null)).toEqual([
      'skills',
      'search',
      'anonymous',
      { q: 'agent', sort: 'newest' },
      'zh-CN',
    ])
    expect(getSkillLabelsQueryKey('team', 'demo')).toEqual(['labels', 'skill', 'team', 'demo', 'zh-CN'])
    expect(getSkillDetailQueryKey('team', 'demo')).toEqual(['skills', 'team', 'demo', 'zh-CN'])
    expect(getAdminLabelDefinitionsQueryKey()).toEqual(['labels', 'admin', 'zh-CN'])
  })
})

describe('useUpdateSkillVisibility', () => {
  it('updates visibility and invalidates all affected skill query families', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        mutations: { retry: false },
        queries: { retry: false },
      },
    })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    updateVisibilityMock.mockResolvedValue({
      skillId: 101,
      visibility: 'NAMESPACE_ONLY',
      changed: true,
    })
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children)
    const { result } = renderHook(() => useUpdateSkillVisibility(), { wrapper })

    await result.current.mutateAsync({
      namespace: 'team-ai',
      slug: 'demo',
      visibility: 'NAMESPACE_ONLY',
    })

    expect(updateVisibilityMock).toHaveBeenCalledWith('team-ai', 'demo', 'NAMESPACE_ONLY')
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['skills', 'my'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['skills', 'team-ai', 'demo'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['skills', 'team-ai', 'demo', 'versions'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['skills'] })
  })
})

describe('protected skill content queries', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps disabled README and file queries idle and locally handled', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, wrapper } = createQueryHarness()

    const { result } = renderHook(() => ({
      readme: useSkillReadme('global', 'demo', '1.0.0', 'SKILL.md', false),
      file: useSkillFile('global', 'demo', '1.0.0', 'docs/usage.md', false),
    }), { wrapper })

    expect(result.current.readme.fetchStatus).toBe('idle')
    expect(result.current.file.fetchStatus).toBe('idle')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(queryClient.getQueryCache().find({
      queryKey: ['skills', 'global', 'demo', 'versions', '1.0.0', 'readme', 'SKILL.md'],
      exact: true,
    })?.meta).toMatchObject({ skipGlobalErrorHandler: true })
    expect(queryClient.getQueryCache().find({
      queryKey: ['skills', 'global', 'demo', 'versions', '1.0.0', 'file', 'docs/usage.md'],
      exact: true,
    })?.meta).toMatchObject({ skipGlobalErrorHandler: true })
  })

  it('fetches protected file content after the query is enabled', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => '# Usage',
    })
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, wrapper } = createQueryHarness()

    const { result } = renderHook(
      () => useSkillFile('global', 'demo', '1.0.0', 'docs/usage.md', true),
      { wrapper },
    )

    await waitFor(() => expect(result.current.data).toBe('# Usage'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(queryClient.getQueryCache().find({
      queryKey: ['skills', 'global', 'demo', 'versions', '1.0.0', 'file', 'docs/usage.md'],
      exact: true,
    })?.meta).toMatchObject({ skipGlobalErrorHandler: true })
  })
})

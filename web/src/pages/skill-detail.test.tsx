/** @vitest-environment jsdom */
import { renderToStaticMarkup } from 'react-dom/server'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { MouseEvent, ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigateMock = vi.fn()
const hasRoleMock = vi.fn<(role: string) => boolean>((role: string) => role === 'USER')
const useSkillDetailMock = vi.fn()
const useSkillLabelsMock = vi.fn()
const useSkillFilesMock = vi.fn()
const useSkillReadmeMock = vi.fn()
const useSkillFileMock = vi.fn()
const useSkillVersionsMock = vi.fn()
const useResourceDiagnosticsMock = vi.fn()
const {
  confirmPublishMutationMock,
  submitForReviewMutationMock,
  toastErrorMock,
  toastSuccessMock,
  updateVisibilityMutationMock,
} = vi.hoisted(() => ({
  confirmPublishMutationMock: vi.fn(),
  submitForReviewMutationMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  updateVisibilityMutationMock: vi.fn(),
}))
let playgroundEnabled = false
let routerLocation = { pathname: '/space/global/demo-skill', searchStr: '', hash: '' }
let authState: {
  user: { userId: string; platformRoles: string[] } | null
  isLoading: boolean
  hasRole: (role: string) => boolean
} = {
  user: { userId: 'owner-1', platformRoles: ['USER'] },
  isLoading: false,
  hasRole: hasRoleMock,
}

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  useParams: () => ({ namespace: 'global', slug: 'demo-skill' }),
  useRouterState: () => routerLocation,
  useSearch: () => ({ returnTo: '/dashboard/skills' }),
  Link: ({
    to,
    search,
    children,
    className,
  }: {
    to: string
    search?: Record<string, unknown>
    children?: ReactNode
    className?: string
  }) => (
    <a href={to} data-search={JSON.stringify(search ?? {})} className={className}>
      {children}
    </a>
  ),
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: { language: 'zh' },
    }),
  }
})

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: null, isLoading: false, error: null }),
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/features/auth/use-auth', () => ({
  useAuth: () => authState,
}))

vi.mock('@/features/report/use-skill-reports', () => ({
  useSubmitSkillReport: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('@/shared/lib/toast', () => ({
  toast: { success: toastSuccessMock, error: toastErrorMock },
}))

vi.mock('@/shared/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
  }: {
    value?: string
    onValueChange?: (value: string) => void
  }) => (
    <select
      aria-label="skillDetail.visibilityLabel"
      value={value}
      onChange={(event) => onValueChange?.(event.target.value)}
    >
      <option value="PUBLIC">PUBLIC</option>
      <option value="NAMESPACE_ONLY">NAMESPACE_ONLY</option>
      <option value="PRIVATE">PRIVATE</option>
    </select>
  ),
  SelectContent: ({ children }: { children: unknown }) => children,
  SelectItem: ({ children }: { children: unknown }) => children,
  SelectTrigger: ({ children }: { children: unknown }) => children,
  SelectValue: () => null,
}))

vi.mock('@/shared/components/confirm-dialog', () => ({
  ConfirmDialog: ({
    open,
    confirmText,
    onConfirm,
  }: {
    open: boolean
    confirmText: string
    onConfirm: () => void
  }) => open
    ? <button type="button" onClick={onConfirm}>{`confirm:${confirmText}`}</button>
    : null,
}))

vi.mock('@/api/client', () => ({
  adminApi: {
    hideSkill: vi.fn(),
    unhideSkill: vi.fn(),
    yankVersion: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number
    serverMessageKey?: string

    constructor(message: string, status: number) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
  buildApiUrl: (value: string) => value,
  WEB_API_PREFIX: '/api/web',
  getPlaygroundRuntimeConfig: () => playgroundEnabled
    ? { enabled: true, baseUrl: 'http://localhost:8091' }
    : { enabled: false },
}))

vi.mock('@/shared/lib/date-time', () => ({
  formatLocalDateTime: (value: string) => value,
}))

vi.mock('@/shared/lib/skill-download-cache', () => ({
  incrementSkillDownloadCount: vi.fn(),
}))

vi.mock('@/shared/lib/number-format', () => ({
  formatCompactCount: (value: number) => String(value),
}))

vi.mock('@/features/skill/markdown-renderer', () => ({
  MarkdownRenderer: ({ onLinkClick }: { onLinkClick?: (href: string, event: MouseEvent<HTMLAnchorElement>) => void }) => (
    <div>
      markdown
      {onLinkClick ? (
        <a href="docs/usage.md" onClick={(event) => onLinkClick('docs/usage.md', event)}>
          Usage
        </a>
      ) : null}
    </div>
  ),
}))

vi.mock('@/features/skill/file-preview-dialog', () => ({
  FilePreviewDialog: ({
    open,
    node,
    onLinkClick,
  }: {
    open: boolean
    node: { path: string } | null
    onLinkClick?: (href: string, event: MouseEvent<HTMLAnchorElement>) => void
  }) => (
    open && node
      ? (
          <div role="dialog">
            preview:{node.path}
            {onLinkClick ? (
              <a href="nested.md" onClick={(event) => onLinkClick('nested.md', event)}>
                Nested
              </a>
            ) : null}
          </div>
        )
      : null
  ),
}))

vi.mock('@/features/skill/file-tree', () => ({
  FileTree: ({
    onFileClick,
  }: {
    onFileClick?: (node: {
      id: string
      name: string
      path: string
      type: 'file'
      depth: number
    }) => void
  }) => (
    <button
      type="button"
      onClick={() => onFileClick?.({
        id: 'SKILL.md',
        name: 'SKILL.md',
        path: 'SKILL.md',
        type: 'file',
        depth: 0,
      })}
    >
      SKILL.md
    </button>
  ),
}))

vi.mock('@/features/skill/install-command', () => ({
  InstallCommand: () => <div>install</div>,
}))

vi.mock('@/features/skill/use-resource-diagnostics', () => ({
  useResourceDiagnostics: (...args: unknown[]) => useResourceDiagnosticsMock(...args),
}))

vi.mock('@/features/social/rating-input', () => ({
  RatingInput: () => <div>__RATING_WIDGET__</div>,
}))

vi.mock('@/features/social/star-button', () => ({
  StarButton: () => <div>__STAR_WIDGET__</div>,
}))

vi.mock('@/shared/hooks/use-skill-queries', () => ({
  useSkillDetail: () => useSkillDetailMock(),
  useSkillLabels: () => useSkillLabelsMock(),
  useVisibleLabels: () => ({
    data: [{ slug: 'code-generation', type: 'RECOMMENDED', displayName: 'Code Generation' }],
    isLoading: false,
  }),
  useAdminLabelDefinitions: () => ({ data: [], isLoading: false }),
  useAttachSkillLabel: () => ({ mutate: vi.fn(), isPending: false }),
  useDetachSkillLabel: () => ({ mutate: vi.fn(), isPending: false }),
  useSkillVersions: (...args: unknown[]) => useSkillVersionsMock(...args),
  useSkillVersionDetail: () => ({ data: undefined }),
  useSkillFiles: () => useSkillFilesMock(),
  useSkillReadme: (...args: unknown[]) => useSkillReadmeMock(...args),
  useSkillFile: (...args: unknown[]) => useSkillFileMock(...args),
  useArchiveSkill: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSkill: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSkillVersion: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRereleaseSkillVersion: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUnarchiveSkill: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useWithdrawSkillReview: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSubmitForReview: () => ({ mutateAsync: submitForReviewMutationMock, isPending: false }),
  useConfirmPublish: () => ({ mutateAsync: confirmPublishMutationMock, isPending: false }),
  useUpdateSkillVisibility: () => ({ mutateAsync: updateVisibilityMutationMock, isPending: false }),
}))

vi.mock('@/shared/hooks/use-label-queries', () => ({
  useSkillLabels: () => useSkillLabelsMock(),
  useVisibleLabels: () => ({
    data: [{ slug: 'code-generation', type: 'RECOMMENDED', displayName: 'Code Generation' }],
    isLoading: false,
  }),
  useAdminLabelDefinitions: () => ({ data: [], isLoading: false }),
  useAttachSkillLabel: () => ({ mutate: vi.fn(), isPending: false }),
  useDetachSkillLabel: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/shared/hooks/use-user-queries', () => ({
  useSubmitPromotion: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

import { ApiError } from '@/api/client'
import { SkillDetailPage } from './skill-detail'

function createSkill(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    slug: 'demo-skill',
    displayName: 'Demo Skill',
    ownerId: 'owner-1',
    ownerDisplayName: 'Owner One',
    summary: 'summary',
    visibility: 'PUBLIC',
    status: 'ACTIVE',
    downloadCount: 12,
    starCount: 2,
    ratingAvg: 4.5,
    ratingCount: 2,
    hidden: false,
    namespace: 'global',
    canManageLifecycle: true,
    platformAdminOverride: false,
    canSubmitPromotion: false,
    canInteract: true,
    canReport: true,
    headlineVersion: { id: 10, version: '1.0.0', status: 'PUBLISHED' },
    publishedVersion: { id: 10, version: '1.0.0', status: 'PUBLISHED' },
    ownerPreviewVersion: undefined,
    resolutionMode: 'PUBLISHED',
    ...overrides,
  }
}

describe('SkillDetailPage', () => {
  afterEach(() => {
    cleanup()
    delete window.__SKILLHUB_RUNTIME_CONFIG__
  })

  beforeEach(() => {
    navigateMock.mockReset()
    playgroundEnabled = false
    routerLocation = { pathname: '/space/global/demo-skill', searchStr: '', hash: '' }
    hasRoleMock.mockImplementation((role: string) => role === 'USER')
    authState = {
      user: { userId: 'owner-1', platformRoles: ['USER'] },
      isLoading: false,
      hasRole: hasRoleMock,
    }
    useSkillDetailMock.mockReturnValue({
      data: createSkill(),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useSkillVersionsMock.mockReturnValue({
      data: [
        {
          id: 10,
          version: '1.0.0',
          status: 'PUBLISHED',
          changelog: '',
          fileCount: 1,
          totalSize: 12,
          publishedAt: '2026-03-20T00:00:00Z',
          downloadAvailable: true,
        },
      ],
    })
    useSkillLabelsMock.mockReturnValue({
      data: undefined,
    })
    useSkillFilesMock.mockReturnValue({ data: [] })
    useSkillReadmeMock.mockReset()
    useSkillReadmeMock.mockReturnValue({ data: '# Demo', isLoading: false, error: null })
    useSkillFileMock.mockReset()
    useSkillFileMock.mockReturnValue({ data: null, isLoading: false, error: null })
    useResourceDiagnosticsMock.mockReturnValue({ data: undefined, isLoading: false, error: null })
    confirmPublishMutationMock.mockReset()
    confirmPublishMutationMock.mockResolvedValue(undefined)
    submitForReviewMutationMock.mockReset()
    submitForReviewMutationMock.mockResolvedValue(undefined)
    updateVisibilityMutationMock.mockReset()
    updateVisibilityMutationMock.mockResolvedValue({
      skillId: 1,
      visibility: 'NAMESPACE_ONLY',
      changed: true,
    })
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
  })

  it('shows hard delete action for the skill owner', () => {
    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).toContain('skillDetail.deleteSkill')
  })

  it('hides hard delete action when the viewer is not the owner or super admin', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({ ownerId: 'someone-else' }),
      isLoading: false,
      error: null,
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).not.toContain('skillDetail.deleteSkill')
  })

  it('runs resource diagnostics only after a platform admin requests them', () => {
    authState = {
      user: { userId: 'platform-admin', platformRoles: ['SUPER_ADMIN'] },
      isLoading: false,
      hasRole: (role: string) => role === 'SUPER_ADMIN',
    }
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        ownerId: 'someone-else',
        canManageLifecycle: false,
        platformAdminOverride: true,
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useResourceDiagnosticsMock.mockReturnValue({
      data: {
        skillId: 1,
        namespace: 'global',
        slug: 'demo-skill',
        namespaceStatus: 'ACTIVE',
        latestVersionId: 10,
        versionCount: 1,
        fileCount: 0,
        blankStorageKeyCount: 0,
        checkedObjectCount: 1,
        checkedFileObjectCount: 0,
        uncheckedFileObjectCount: 0,
        missingObjects: [{ path: 'bundle:1.0.0', storageKey: 'packages/1/10/bundle.zip' }],
        storageProbeError: null,
        diagnosticStatus: 'MISSING_OBJECTS',
      },
      isLoading: false,
      error: null,
    })

    render(<SkillDetailPage />)

    expect(screen.getByText('skillDetail.resourceDiagnosticsTitle')).toBeTruthy()
    expect(screen.getByText('skillDetail.runResourceDiagnostics')).toBeTruthy()
    expect(screen.queryByText('MISSING_OBJECTS')).toBeNull()
    expect(useResourceDiagnosticsMock).toHaveBeenLastCalledWith(1, false)

    fireEvent.click(screen.getByText('skillDetail.runResourceDiagnostics'))

    expect(screen.getByText('MISSING_OBJECTS')).toBeTruthy()
    expect(screen.getByText('skillDetail.deleteSkill')).toBeTruthy()
    expect(screen.queryByText('skillDetail.archiveSkill')).toBeNull()
    expect(useResourceDiagnosticsMock).toHaveBeenLastCalledWith(1, true)
  })

  it('renders public skill details for an anonymous viewer', () => {
    authState = {
      user: null,
      isLoading: false,
      hasRole: vi.fn(() => false),
    }

    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        canManageLifecycle: false,
        canInteract: true,
        visibility: 'PUBLIC',
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useSkillFilesMock.mockReturnValue({
      data: [{
        id: 1,
        filePath: 'SKILL.md',
        fileSize: 128,
        contentType: 'text/markdown',
        sha256: 'readme',
      }],
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).toContain('Demo Skill')
    expect(html).toContain('install')
    expect(html).toContain('skillDetail.readmeLoginRequiredTitle')
    expect(html).toContain('skillDetail.signInToView')
    expect(html).not.toContain('skillDetail.loginRequired')
    expect(html).not.toContain('skillDetail.deleteSkill')
    expect(html).not.toContain('markdown')
    expect(useSkillReadmeMock).toHaveBeenCalledWith(
      'global',
      'demo-skill',
      '1.0.0',
      'SKILL.md',
      false,
    )
  })

  it('routes anonymous README and file actions to login with the exact return target', () => {
    authState = {
      user: null,
      isLoading: false,
      hasRole: vi.fn(() => false),
    }
    useSkillDetailMock.mockReturnValue({
      data: createSkill({ canManageLifecycle: false }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useSkillFilesMock.mockReturnValue({
      data: [{
        id: 1,
        filePath: 'SKILL.md',
        fileSize: 128,
        contentType: 'text/markdown',
        sha256: 'readme',
      }],
    })

    render(<SkillDetailPage />)

    fireEvent.click(screen.getByText('skillDetail.signInToView'))
    expect(navigateMock).toHaveBeenLastCalledWith({
      to: '/login',
      search: { returnTo: '/space/global/demo-skill' },
    })

    navigateMock.mockReset()
    fireEvent.click(screen.getByRole('tab', { name: 'skillDetail.tabFiles' }))
    expect(screen.getAllByText('skillDetail.filesLoginRequired').length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByRole('button', { name: 'SKILL.md' })[0])

    expect(navigateMock).toHaveBeenLastCalledWith({
      to: '/login',
      search: { returnTo: '/space/global/demo-skill' },
    })
    expect(useSkillFileMock).toHaveBeenLastCalledWith(
      'global',
      'demo-skill',
      '1.0.0',
      null,
      false,
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('normalizes a browser-prefixed return target through the shared auth route helper', () => {
    window.__SKILLHUB_RUNTIME_CONFIG__ = { basePath: '/skillhub' }
    routerLocation = {
      pathname: '/skillhub/space/global/demo-skill',
      searchStr: '?returnTo=%2Fsearch%3Fq%3Ddemo',
      hash: '#readme',
    }
    authState = {
      user: null,
      isLoading: false,
      hasRole: vi.fn(() => false),
    }

    render(<SkillDetailPage />)
    fireEvent.click(screen.getByText('skillDetail.signInToView'))

    expect(navigateMock).toHaveBeenLastCalledWith({
      to: '/login',
      search: {
        returnTo: '/space/global/demo-skill?returnTo=%2Fsearch%3Fq%3Ddemo#readme',
      },
    })
  })

  it('uses a neutral protected-content state while authentication is loading', () => {
    authState = {
      user: null,
      isLoading: true,
      hasRole: vi.fn(() => false),
    }
    useSkillFilesMock.mockReturnValue({
      data: [{
        id: 1,
        filePath: 'SKILL.md',
        fileSize: 128,
        contentType: 'text/markdown',
        sha256: 'readme',
      }],
    })

    render(<SkillDetailPage />)

    expect(screen.getByRole('heading', { name: 'Demo Skill' })).toBeTruthy()
    expect(screen.queryByText('skillDetail.readmeLoginRequiredTitle')).toBeNull()
    expect(screen.queryByText('markdown')).toBeNull()
    expect(useSkillReadmeMock).toHaveBeenCalledWith(
      'global',
      'demo-skill',
      '1.0.0',
      'SKILL.md',
      false,
    )
  })

  it('keeps protected content available for authenticated viewers', () => {
    useSkillFilesMock.mockReturnValue({
      data: [{
        id: 1,
        filePath: 'SKILL.md',
        fileSize: 128,
        contentType: 'text/markdown',
        sha256: 'readme',
      }],
    })

    render(<SkillDetailPage />)

    expect(screen.getByText('markdown')).toBeTruthy()
    expect(useSkillReadmeMock).toHaveBeenCalledWith(
      'global',
      'demo-skill',
      '1.0.0',
      'SKILL.md',
      true,
    )
  })

  it('renders a local session-expired action for an authenticated README request', () => {
    useSkillFilesMock.mockReturnValue({
      data: [{
        id: 1,
        filePath: 'SKILL.md',
        fileSize: 128,
        contentType: 'text/markdown',
        sha256: 'readme',
      }],
    })
    useSkillReadmeMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new ApiError('error.auth.required', 401),
    })

    render(<SkillDetailPage />)

    expect(screen.getByText('skillDetail.sessionExpiredTitle')).toBeTruthy()
    fireEvent.click(screen.getByText('skillDetail.signInAgain'))
    expect(navigateMock).toHaveBeenLastCalledWith({
      to: '/login',
      search: { returnTo: '/space/global/demo-skill' },
    })
    expect(toastErrorMock).not.toHaveBeenCalled()
  })

  it('hides Try in Playground when runtime config is disabled', () => {
    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).not.toContain('skillDetail.tryInPlayground')
  })

  it('shows Try in Playground for a visible selected skill when enabled', () => {
    playgroundEnabled = true

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).toContain('skillDetail.tryInPlayground')
  })

  it('shows the label management panel for a user who can manage the skill lifecycle', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        labels: [{ slug: 'official', type: 'RECOMMENDED', displayName: 'Official' }],
      }),
      isLoading: false,
      error: null,
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).toContain('skillDetail.labelsSectionTitle')
    expect(html).toContain('skillDetail.removeLabel')
    expect(html).toContain('skillDetail.addLabel')
  })

  it('links skill label chips to a search filtered by that label', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        ownerId: 'someone-else',
        canManageLifecycle: false,
        labels: [{ slug: 'code-generation', type: 'RECOMMENDED', displayName: 'Code Generation' }],
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).toContain('href="/search"')
    expect(html).toContain('&quot;label&quot;:&quot;code-generation&quot;')
    expect(html).toContain('Code Generation')
  })

  it('hides the label management panel when the viewer lacks label permissions', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        ownerId: 'someone-else',
        canManageLifecycle: false,
      }),
      isLoading: false,
      error: null,
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).not.toContain('skillDetail.labelsSectionTitle')
  })

  it('shows the current visibility control only to lifecycle managers', () => {
    const { rerender } = render(<SkillDetailPage />)

    const select = screen.getByLabelText('skillDetail.visibilityLabel') as HTMLSelectElement
    expect(select.value).toBe('PUBLIC')
    expect(screen.getByText('skillDetail.saveVisibility').closest('button')?.disabled).toBe(true)

    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        ownerId: 'someone-else',
        canManageLifecycle: false,
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    rerender(<SkillDetailPage />)

    expect(screen.queryByLabelText('skillDetail.visibilityLabel')).toBeNull()
  })

  it('keeps visibility controls stacked within the narrow lifecycle sidebar', () => {
    render(<SkillDetailPage />)

    const controls = screen.getByTestId('skill-visibility-controls')
    expect(controls.className).toContain('grid-cols-1')
    expect(controls.className).not.toContain('sm:flex-row')
    expect(screen.getByText('skillDetail.saveVisibility').closest('button')?.className).toContain('w-full')
  })

  it('updates visibility without triggering publish or review transitions', async () => {
    render(<SkillDetailPage />)

    fireEvent.change(screen.getByLabelText('skillDetail.visibilityLabel'), {
      target: { value: 'NAMESPACE_ONLY' },
    })
    fireEvent.click(screen.getByText('skillDetail.saveVisibility'))

    await waitFor(() => {
      expect(updateVisibilityMutationMock).toHaveBeenCalledWith({
        namespace: 'global',
        slug: 'demo-skill',
        visibility: 'NAMESPACE_ONLY',
      })
    })
    expect(submitForReviewMutationMock).not.toHaveBeenCalled()
    expect(confirmPublishMutationMock).not.toHaveBeenCalled()
    expect(toastSuccessMock).toHaveBeenCalledWith(
      'skillDetail.visibilityUpdateSuccessTitle',
      'skillDetail.visibilityUpdateSuccessDescription',
    )
  })

  it('shows an error toast when visibility update fails', async () => {
    updateVisibilityMutationMock.mockRejectedValue(new Error('network failed'))
    render(<SkillDetailPage />)

    fireEvent.change(screen.getByLabelText('skillDetail.visibilityLabel'), {
      target: { value: 'PRIVATE' },
    })
    fireEvent.click(screen.getByText('skillDetail.saveVisibility'))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        'skillDetail.visibilityUpdateErrorTitle',
        'network failed',
      )
    })
  })

  it.each([
    ['PUBLIC', 'PUBLIC'],
    ['NAMESPACE_ONLY', 'NAMESPACE_ONLY'],
  ] as const)('submits an uploaded %s skill for review with its current visibility', async (visibility, targetVisibility) => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        visibility,
        headlineVersion: { id: 11, version: '1.1.0', status: 'UPLOADED' },
        publishedVersion: undefined,
        ownerPreviewVersion: { id: 11, version: '1.1.0', status: 'UPLOADED' },
        resolutionMode: 'OWNER_PREVIEW',
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useSkillVersionsMock.mockReturnValue({
      data: [{
        id: 11,
        version: '1.1.0',
        status: 'UPLOADED',
        changelog: '',
        fileCount: 1,
        totalSize: 12,
        publishedAt: null,
        downloadAvailable: false,
      }],
    })
    render(<SkillDetailPage />)
    fireEvent.click(screen.getByText('skillDetail.tabVersions'))

    expect(screen.queryByText('skillDetail.confirmPublish')).toBeNull()
    fireEvent.click(screen.getByText('skillDetail.submitReview'))
    fireEvent.click(screen.getByText('confirm:skillDetail.submitReview'))

    await waitFor(() => {
      expect(submitForReviewMutationMock).toHaveBeenCalledWith({
        namespace: 'global',
        slug: 'demo-skill',
        version: '1.1.0',
        targetVisibility,
      })
    })
    expect(confirmPublishMutationMock).not.toHaveBeenCalled()
  })

  it('keeps direct publish for an uploaded private skill', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        visibility: 'PRIVATE',
        headlineVersion: { id: 11, version: '1.1.0', status: 'UPLOADED' },
        publishedVersion: undefined,
        ownerPreviewVersion: { id: 11, version: '1.1.0', status: 'UPLOADED' },
        resolutionMode: 'OWNER_PREVIEW',
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useSkillVersionsMock.mockReturnValue({
      data: [{
        id: 11,
        version: '1.1.0',
        status: 'UPLOADED',
        changelog: '',
        fileCount: 1,
        totalSize: 12,
        publishedAt: null,
        downloadAvailable: false,
      }],
    })

    render(<SkillDetailPage />)
    fireEvent.click(screen.getByText('skillDetail.tabVersions'))

    expect(screen.getByText('skillDetail.confirmPublish')).toBeTruthy()
    expect(screen.queryByText('skillDetail.submitReview')).toBeNull()
  })

  it('does not render dependent social controls while the detail query is still refetching', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill(),
      isLoading: false,
      isFetching: true,
      error: null,
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(useSkillVersionsMock).toHaveBeenCalledWith('global', 'demo-skill', false)
    expect(html).not.toContain('__STAR_WIDGET__')
    expect(html).not.toContain('__RATING_WIDGET__')
  })

  it('renders rejected owner preview without pending-review copy', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        canInteract: false,
        headlineVersion: { id: 11, version: '1.1.0', status: 'REJECTED' },
        publishedVersion: undefined,
        ownerPreviewVersion: { id: 11, version: '1.1.0', status: 'REJECTED' },
        resolutionMode: 'OWNER_PREVIEW',
        ownerPreviewReviewComment: 'manifest validation failed',
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useSkillVersionsMock.mockReturnValue({
      data: [
        {
          id: 11,
          version: '1.1.0',
          status: 'REJECTED',
          changelog: '',
          fileCount: 1,
          totalSize: 12,
          publishedAt: null,
          downloadAvailable: false,
        },
      ],
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).toContain('skillDetail.rejectedBadge')
    expect(html).toContain('skillDetail.rejectedFeedbackTitle')
    expect(html).toContain('manifest validation failed')
    expect(html).not.toContain('skillDetail.pendingPreviewBadge')
    expect(html).not.toContain('skillDetail.pendingPreviewTitle')
  })

  it('renders pending review status in the header for scan-failed owner preview versions', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        canInteract: false,
        headlineVersion: { id: 12, version: '1.2.0', status: 'SCAN_FAILED' },
        publishedVersion: undefined,
        ownerPreviewVersion: { id: 12, version: '1.2.0', status: 'SCAN_FAILED' },
        resolutionMode: 'OWNER_PREVIEW',
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useSkillVersionsMock.mockReturnValue({
      data: [
        {
          id: 12,
          version: '1.2.0',
          status: 'SCAN_FAILED',
          changelog: '',
          fileCount: 1,
          totalSize: 12,
          publishedAt: null,
          downloadAvailable: false,
        },
      ],
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).toContain('skillDetail.versionStatusPendingReview')
    expect(html).not.toContain('skillDetail.versionStatusScanFailed')
  })

  it('allows long pending review versions to wrap inside the review card', () => {
    useSkillDetailMock.mockReturnValue({
      data: createSkill({
        headlineVersion: { id: 13, version: '20260326.055640-build-with-very-long-suffix', status: 'PENDING_REVIEW' },
        publishedVersion: { id: 10, version: '20260326.055538', status: 'PUBLISHED' },
        ownerPreviewVersion: { id: 13, version: '20260326.055640-build-with-very-long-suffix', status: 'PENDING_REVIEW' },
        resolutionMode: 'PUBLISHED',
      }),
      isLoading: false,
      isFetching: false,
      error: null,
    })
    useSkillVersionsMock.mockReturnValue({
      data: [
        {
          id: 13,
          version: '20260326.055640-build-with-very-long-suffix',
          status: 'PENDING_REVIEW',
          changelog: '',
          fileCount: 1,
          totalSize: 12,
          publishedAt: null,
          downloadAvailable: false,
        },
        {
          id: 10,
          version: '20260326.055538',
          status: 'PUBLISHED',
          changelog: '',
          fileCount: 1,
          totalSize: 12,
          publishedAt: '2026-03-20T00:00:00Z',
          downloadAvailable: true,
        },
      ],
    })

    const html = renderToStaticMarkup(<SkillDetailPage />)

    expect(html).toContain('break-all')
    expect(html).toContain('leading-snug')
  })

  it('resolves links inside previewed markdown files against the previewed file path', () => {
    useSkillFilesMock.mockReturnValue({
      data: [
        {
          id: 1,
          filePath: 'README.md',
          fileSize: 128,
          contentType: 'text/markdown',
          sha256: 'readme',
        },
        {
          id: 2,
          filePath: 'docs/usage.md',
          fileSize: 128,
          contentType: 'text/markdown',
          sha256: 'usage',
        },
        {
          id: 3,
          filePath: 'docs/nested.md',
          fileSize: 128,
          contentType: 'text/markdown',
          sha256: 'nested',
        },
      ],
    })

    render(<SkillDetailPage />)
    fireEvent.click(screen.getByRole('link', { name: 'Usage' }))
    expect(screen.getByRole('dialog').textContent).toContain('preview:docs/usage.md')

    fireEvent.click(screen.getByRole('link', { name: 'Nested' }))

    expect(screen.getByRole('dialog').textContent).toContain('preview:docs/nested.md')
  })
})

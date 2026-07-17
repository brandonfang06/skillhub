/** @vitest-environment jsdom */
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import type { ManagedNamespace } from '@/api/types'

const navigateMock = vi.fn()
const freezeMutateAsync = vi.fn()
const unfreezeMutateAsync = vi.fn()
const archiveMutateAsync = vi.fn()
const restoreMutateAsync = vi.fn()
const deleteMutateAsync = vi.fn()

let mockNamespaces: ManagedNamespace[] = []

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, options?: Record<string, unknown>) => key === 'myNamespaces.resultCount'
        ? `${options?.matched}/${options?.total}`
        : key,
    }),
  }
})

vi.mock('@/features/auth/use-auth', () => ({
  useAuth: () => ({ hasRole: () => false }),
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children, ...props }: { children: ReactNode }) => createElement('button', props, children),
}))

vi.mock('@/shared/ui/card', () => ({
  Card: ({ children, ...props }: { children: ReactNode }) => createElement('div', props, children),
}))

vi.mock('@/shared/ui/select', () => ({
  Select: ({
    children,
    value,
    onValueChange,
  }: {
    children: ReactNode
    value: string
    onValueChange?: (value: string) => void
  }) => createElement('select', {
    'aria-label': 'myNamespaces.statusFilterLabel',
    value,
    onChange: (event: { target: { value: string } }) => onValueChange?.(event.target.value),
  }, children),
  SelectContent: ({ children }: { children: ReactNode }) => children,
  SelectItem: ({ children, value }: { children: ReactNode; value: string }) => createElement('option', { value }, children),
  SelectTrigger: ({ children }: { children: ReactNode }) => children,
  SelectValue: () => null,
}))

vi.mock('@/shared/components/namespace-badge', () => ({
  NamespaceBadge: ({ name }: { name: string }) => createElement('span', null, name),
}))

vi.mock('@/shared/components/empty-state', () => ({
  EmptyState: ({ title, description, action }: { title: string; description: string; action?: ReactNode }) => createElement(
    'section',
    null,
    createElement('h2', null, title),
    createElement('p', null, description),
    action,
  ),
}))

vi.mock('@/shared/components/confirm-dialog', () => ({
  ConfirmDialog: () => null,
}))

vi.mock('@/shared/components/dashboard-page-header', () => ({
  DashboardPageHeader: ({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) => createElement(
    'header',
    null,
    title,
    subtitle,
    actions,
  ),
}))

vi.mock('@/features/namespace/create-namespace-dialog', () => ({
  CreateNamespaceDialog: ({ children }: { children: ReactNode }) => children,
}))

vi.mock('@/shared/hooks/use-namespace-queries', () => ({
  useArchiveNamespace: () => ({ mutateAsync: archiveMutateAsync }),
  useDeleteNamespace: () => ({ mutateAsync: deleteMutateAsync }),
  useFreezeNamespace: () => ({ mutateAsync: freezeMutateAsync }),
  useMyNamespaces: () => ({ data: mockNamespaces, isLoading: false }),
  useRestoreNamespace: () => ({ mutateAsync: restoreMutateAsync }),
  useUnfreezeNamespace: () => ({ mutateAsync: unfreezeMutateAsync }),
}))

vi.mock('@/shared/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import {
  executeNamespaceAction,
  filterManagedNamespaces,
  MyNamespacesPage,
  resolveNamespaceActionCopy,
} from './my-namespaces'

function buildNamespace(overrides: Partial<ManagedNamespace> = {}): ManagedNamespace {
  return {
    id: 1,
    slug: 'team-ml',
    displayName: 'Team ML',
    description: 'namespace',
    type: 'TEAM',
    status: 'ACTIVE',
    createdAt: '2026-05-07T00:00:00Z',
    immutable: false,
    canFreeze: false,
    canUnfreeze: false,
    canArchive: false,
    canRestore: false,
    deleteAuthorized: false,
    canDelete: false,
    deleteBlockers: { skillCount: 0, reviewTaskCount: 0, promotionRequestCount: 0 },
    ...overrides,
  }
}

describe('MyNamespacesPage', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    navigateMock.mockReset()
    freezeMutateAsync.mockReset()
    unfreezeMutateAsync.mockReset()
    archiveMutateAsync.mockReset()
    restoreMutateAsync.mockReset()
    deleteMutateAsync.mockReset()
    mockNamespaces = []
  })

  it('exports a named component function', () => {
    expect(typeof MyNamespacesPage).toBe('function')
  })

  it('matches namespace display names and slugs without case sensitivity', () => {
    const namespaces = [
      buildNamespace({ id: 1, slug: 'product-alpha', displayName: 'Product Alpha' }),
      buildNamespace({ id: 2, slug: 'data-platform', displayName: 'Analytics Team' }),
    ]

    expect(filterManagedNamespaces(namespaces, { query: '  PRODUCT  ', status: 'ALL' }))
      .toEqual([namespaces[0]])
    expect(filterManagedNamespaces(namespaces, { query: '@DATA-PLATFORM', status: 'ALL' }))
      .toEqual([namespaces[1]])
    expect(filterManagedNamespaces(namespaces, { query: 'data-platform', status: 'ALL' }))
      .toEqual([namespaces[1]])
  })

  it('normalizes case independently from the browser locale', () => {
    const namespace = buildNamespace({ slug: 'ISTANBUL', displayName: 'Unrelated' })
    const localeLowerCase = vi.spyOn(String.prototype, 'toLocaleLowerCase')
      .mockImplementation(() => {
        throw new Error('locale-sensitive normalization called')
      })

    try {
      expect(filterManagedNamespaces([namespace], { query: 'istanbul', status: 'ALL' }))
        .toEqual([namespace])
    } finally {
      localeLowerCase.mockRestore()
    }
  })

  it('combines exact status filtering with search and preserves input order', () => {
    const namespaces = [
      buildNamespace({ id: 3, slug: 'product-archived', displayName: 'Product Archived', status: 'ARCHIVED' }),
      buildNamespace({ id: 1, slug: 'product-active', displayName: 'Product Active', status: 'ACTIVE' }),
      buildNamespace({ id: 2, slug: 'product-frozen', displayName: 'Product Frozen', status: 'FROZEN' }),
    ]

    expect(filterManagedNamespaces(namespaces, { query: 'product', status: 'ACTIVE' }))
      .toEqual([namespaces[1]])
    expect(filterManagedNamespaces(namespaces, { query: '', status: 'ALL' }))
      .toEqual(namespaces)
  })

  it('filters rendered namespace cards by search and status and shows the result count', () => {
    mockNamespaces = [
      buildNamespace({ id: 1, slug: 'product-alpha', displayName: 'Product Alpha', status: 'ACTIVE' }),
      buildNamespace({ id: 2, slug: 'data-platform', displayName: 'Data Platform', status: 'ARCHIVED' }),
      buildNamespace({ id: 3, slug: 'data-runtime', displayName: 'Data Runtime', status: 'ACTIVE' }),
    ]
    render(createElement(MyNamespacesPage))

    expect(screen.getByRole('status').textContent).toBe('3/3')

    fireEvent.change(screen.getByLabelText('myNamespaces.searchLabel'), {
      target: { value: '@DATA' },
    })

    expect(screen.queryByTestId('namespace-card-product-alpha')).toBeNull()
    expect(screen.getByTestId('namespace-card-data-platform')).toBeTruthy()
    expect(screen.getByTestId('namespace-card-data-runtime')).toBeTruthy()
    expect(screen.getByText('2/3')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('myNamespaces.statusFilterLabel'), {
      target: { value: 'ARCHIVED' },
    })

    expect(screen.getByTestId('namespace-card-data-platform')).toBeTruthy()
    expect(screen.queryByTestId('namespace-card-data-runtime')).toBeNull()
    expect(screen.getByText('1/3')).toBeTruthy()
  })

  it('returns keyboard focus to the search input after clearing its value', () => {
    mockNamespaces = [buildNamespace()]
    render(createElement(MyNamespacesPage))
    const searchInput = screen.getByLabelText('myNamespaces.searchLabel')

    fireEvent.change(searchInput, { target: { value: 'team' } })
    const clearButton = screen.getByLabelText('myNamespaces.clearSearch')
    clearButton.focus()
    fireEvent.click(clearButton)

    expect(document.activeElement).toBe(searchInput)
  })

  it('preserves permission-gated namespace actions after filtering', () => {
    mockNamespaces = [
      buildNamespace({
        slug: 'product-alpha',
        displayName: 'Product Alpha',
        currentUserRole: 'OWNER',
        canArchive: true,
      }),
      buildNamespace({ id: 2, slug: 'data-platform', displayName: 'Data Platform' }),
    ]
    render(createElement(MyNamespacesPage))

    fireEvent.change(screen.getByLabelText('myNamespaces.searchLabel'), {
      target: { value: 'product-alpha' },
    })

    expect(screen.getByText('myNamespaces.manageMembers')).toBeTruthy()
    expect(screen.getByText('myNamespaces.reviewTasks')).toBeTruthy()
    expect(screen.getByText('myNamespaces.archive')).toBeTruthy()
  })

  it('shows a filter-specific empty state and clears active filters', () => {
    mockNamespaces = [
      buildNamespace({ id: 1, slug: 'product-alpha', displayName: 'Product Alpha' }),
      buildNamespace({ id: 2, slug: 'data-platform', displayName: 'Data Platform' }),
    ]
    render(createElement(MyNamespacesPage))

    fireEvent.change(screen.getByLabelText('myNamespaces.searchLabel'), {
      target: { value: 'missing' },
    })

    expect(screen.getByText('myNamespaces.noMatchTitle')).toBeTruthy()
    expect(screen.queryByTestId('namespace-card-product-alpha')).toBeNull()

    fireEvent.click(screen.getByText('myNamespaces.clearFilters'))

    expect(screen.getByTestId('namespace-card-product-alpha')).toBeTruthy()
    expect(screen.getByTestId('namespace-card-data-platform')).toBeTruthy()
    expect(screen.queryByText('myNamespaces.noMatchTitle')).toBeNull()
  })

  it('renders the delete action when the namespace is deletable', () => {
    mockNamespaces = [buildNamespace({ deleteAuthorized: true, canDelete: true })]

    const html = renderToStaticMarkup(createElement(MyNamespacesPage))

    expect(html).toContain('myNamespaces.delete')
  })

  it('shows a disabled delete action and blockers to an authorized operator', () => {
    mockNamespaces = [buildNamespace({
      deleteAuthorized: true,
      canDelete: false,
      deleteBlockers: { skillCount: 2, reviewTaskCount: 1, promotionRequestCount: 0 },
    })]

    const html = renderToStaticMarkup(createElement(MyNamespacesPage))

    expect(html).toContain('myNamespaces.delete')
    expect(html).toContain('myNamespaces.deleteBlockers')
    expect(html).toContain('disabled')
  })

  it('hides the delete action from an unauthorized viewer', () => {
    mockNamespaces = [buildNamespace({ deleteAuthorized: false, canDelete: false })]

    const html = renderToStaticMarkup(createElement(MyNamespacesPage))

    expect(html).not.toContain('myNamespaces.delete')
  })

  it('hides member and review actions for a platform-admin cleanup-only namespace', () => {
    mockNamespaces = [buildNamespace({ deleteAuthorized: true, currentUserRole: undefined })]

    const html = renderToStaticMarkup(createElement(MyNamespacesPage))

    expect(html).not.toContain('myNamespaces.manageMembers')
    expect(html).not.toContain('myNamespaces.reviewTasks')
    expect(html).toContain('myNamespaces.delete')
  })

  it('routes delete actions to the delete mutation and emits success feedback', async () => {
    const t = (key: string) => key
    const copy = resolveNamespaceActionCopy(t, 'delete', 'Team ML')
    deleteMutateAsync.mockResolvedValueOnce(undefined)
    const success = vi.fn()
    const error = vi.fn()

    await executeNamespaceAction(
      { action: 'delete', slug: 'team-ml', name: 'Team ML' },
      {
        freeze: { mutateAsync: freezeMutateAsync },
        unfreeze: { mutateAsync: unfreezeMutateAsync },
        archive: { mutateAsync: archiveMutateAsync },
        restore: { mutateAsync: restoreMutateAsync },
        delete: { mutateAsync: deleteMutateAsync },
      },
      copy,
      { success, error },
    )

    expect(deleteMutateAsync).toHaveBeenCalledWith({ slug: 'team-ml' })
    expect(success).toHaveBeenCalledWith('myNamespaces.deleteSuccessTitle', 'myNamespaces.deleteSuccessDescription')
    expect(error).not.toHaveBeenCalled()
  })

  it('surfaces delete failures through error feedback and rethrows', async () => {
    const t = (key: string) => key
    const copy = resolveNamespaceActionCopy(t, 'delete', 'Team ML')
    deleteMutateAsync.mockRejectedValueOnce(new Error('blocked'))
    const success = vi.fn()
    const error = vi.fn()

    await expect(executeNamespaceAction(
      { action: 'delete', slug: 'team-ml', name: 'Team ML' },
      {
        freeze: { mutateAsync: freezeMutateAsync },
        unfreeze: { mutateAsync: unfreezeMutateAsync },
        archive: { mutateAsync: archiveMutateAsync },
        restore: { mutateAsync: restoreMutateAsync },
        delete: { mutateAsync: deleteMutateAsync },
      },
      copy,
      { success, error },
    )).rejects.toThrow('blocked')

    expect(error).toHaveBeenCalledWith('myNamespaces.deleteErrorTitle', 'blocked')
    expect(success).not.toHaveBeenCalled()
  })
})

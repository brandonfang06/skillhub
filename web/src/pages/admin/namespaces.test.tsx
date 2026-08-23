// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

afterEach(cleanup)

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, options?: Record<string, unknown>) => options ? `${key}:${JSON.stringify(options)}` : key }),
}))

const summary = {
  id: 1,
  slug: 'platform-tools',
  displayName: 'Platform Tools',
  description: 'Long lived platform skills',
  status: 'ACTIVE' as const,
  type: 'TEAM' as const,
  avatarUrl: null,
  createdBy: 'owner',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-08-23T00:00:00Z',
  stats: { memberCount: 2, skillCount: 5 },
  permissions: {
    currentUserRole: null,
    platformOverride: true,
    immutable: false,
    canManageMembers: true,
    canGovernNamespace: true,
    canPublish: true,
    canTransferOwnership: true,
    canFreeze: true,
    canUnfreeze: false,
    canArchive: true,
    canRestore: false,
  },
}

const adminMember = { id: 2, namespaceId: 1, userId: 'admin', displayName: 'Admin Name', email: 'admin@example.test', role: 'ADMIN' as const, createdAt: '2026-01-01', updatedAt: '2026-01-01' }
const ownerMember = { id: 1, namespaceId: 1, userId: 'owner', displayName: 'Owner Name', email: 'owner@example.test', role: 'OWNER' as const, createdAt: '2026-01-01', updatedAt: '2026-01-01' }
const mockState = vi.hoisted(() => ({
  listItems: [] as Array<Record<string, unknown>>,
  memberPages: new Map<number, { items: unknown[]; total: number; page: number; size: number }>(),
  memberHookCalls: [] as Array<{ slug: string | null; page: number; size: number }>,
  remove: vi.fn(),
  transfer: vi.fn(),
  updateRole: vi.fn(),
  freeze: vi.fn(),
}))

beforeEach(() => {
  mockState.listItems = [summary]
  mockState.memberPages = new Map([[0, { items: [ownerMember, adminMember], total: 2, page: 0, size: 20 }]])
  mockState.memberHookCalls = []
  mockState.remove.mockReset().mockResolvedValue({})
  mockState.transfer.mockReset().mockResolvedValue({})
  mockState.updateRole.mockReset().mockResolvedValue({})
  mockState.freeze.mockReset().mockResolvedValue({})
})

vi.mock('@/features/admin/use-admin-namespaces', () => ({
  useAdminNamespaces: () => ({
    data: { items: mockState.listItems, total: mockState.listItems.length, page: 0, size: 20, stats: { total: 3, active: 1, frozen: 1, archived: 1 } },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useAdminNamespace: (slug: string | null) => ({ data: mockState.listItems.find((item) => item.slug === slug), isLoading: false, isError: false, refetch: vi.fn() }),
  useAdminNamespaceMembers: (slug: string | null, page = 0, size = 20) => {
    mockState.memberHookCalls.push({ slug, page, size })
    return { data: mockState.memberPages.get(page) ?? { items: [], total: 0, page, size }, isLoading: false, isError: false, refetch: vi.fn() }
  },
  useAdminNamespaceCandidates: () => ({ data: [] }),
  useAddAdminNamespaceMember: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAdminNamespaceMemberRole: () => ({ mutateAsync: mockState.updateRole, isPending: false }),
  useRemoveAdminNamespaceMember: () => ({ mutateAsync: mockState.remove, isPending: false }),
  useTransferAdminNamespaceOwnership: () => ({ mutateAsync: mockState.transfer, isPending: false }),
  useFreezeAdminNamespace: () => ({ mutateAsync: mockState.freeze, isPending: false }),
  useUnfreezeAdminNamespace: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useArchiveAdminNamespace: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRestoreAdminNamespace: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

import { AdminNamespacesPage, getAdminNamespaceLifecycleActions } from './namespaces'

describe('AdminNamespacesPage', () => {
  it('renders unfiltered lifecycle cards, filters, namespace detail and real role override', () => {
    const html = renderToStaticMarkup(<AdminNamespacesPage />)

    expect(html).toContain('adminNamespaces.title')
    expect(html).toContain('adminNamespaces.stats.total')
    expect(html).toContain('adminNamespaces.filter.status')
    expect(html).toContain('Platform Tools')
    expect(html).toContain('adminNamespaces.platformOverride')
    expect(html).toContain('adminNamespaces.noMembership')
    expect(html).toContain('Owner Name')
  })

  it('renders only capability-backed active lifecycle actions', () => {
    const html = renderToStaticMarkup(<AdminNamespacesPage />)

    expect(html).toContain('adminNamespaces.actions.freeze')
    expect(html).toContain('adminNamespaces.actions.archive')
    expect(html).not.toContain('adminNamespaces.actions.unfreeze')
    expect(html).not.toContain('adminNamespaces.actions.restore')
  })

  it('maps GLOBAL, ACTIVE, FROZEN and ARCHIVED capabilities without status inference', () => {
    const permissions = summary.permissions
    expect(getAdminNamespaceLifecycleActions({ permissions: { ...permissions, immutable: true } })).toEqual([])
    expect(getAdminNamespaceLifecycleActions({ permissions })).toEqual(['freeze', 'archive'])
    expect(getAdminNamespaceLifecycleActions({ permissions: {
      ...permissions,
      canManageMembers: false,
      canFreeze: false,
      canUnfreeze: true,
      canArchive: true,
    } })).toEqual(['unfreeze', 'archive'])
    expect(getAdminNamespaceLifecycleActions({ permissions: {
      ...permissions,
      canManageMembers: false,
      canFreeze: false,
      canUnfreeze: false,
      canArchive: false,
      canRestore: true,
    } })).toEqual(['restore'])
  })

  it('requires confirmation and exposes the 512-character reason boundary', () => {
    render(<AdminNamespacesPage />)

    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.actions.freeze' }))

    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByLabelText('adminNamespaces.confirm.reason').getAttribute('maxlength')).toBe('512')
    expect(screen.getByRole('button', { name: 'dialog.confirm' })).toBeTruthy()
  })

  it('clears an abandoned lifecycle reason before the next action', () => {
    render(<AdminNamespacesPage />)
    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.actions.freeze' }))
    fireEvent.change(screen.getByLabelText('adminNamespaces.confirm.reason'), { target: { value: 'temporary' } })
    fireEvent.click(screen.getByRole('button', { name: 'dialog.cancel' }))
    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.actions.archive' }))

    expect((screen.getByLabelText('adminNamespaces.confirm.reason') as HTMLTextAreaElement).value).toBe('')
  })

  it('requires confirmation for member removal and ownership transfer', () => {
    render(<AdminNamespacesPage />)

    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.members.remove' }))
    expect(screen.getByText('adminNamespaces.confirm.remove.title')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'dialog.cancel' }))

    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.members.transfer' }))
    expect(screen.getByText('adminNamespaces.confirm.transfer.title')).toBeTruthy()
  })

  it('keeps a confirmed member mutation bound to the namespace selected when opened', async () => {
    const { rerender } = render(<AdminNamespacesPage />)
    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.members.remove' }))

    mockState.listItems = [{ ...summary, id: 9, slug: 'new-first', displayName: 'New First' }, summary]
    rerender(<AdminNamespacesPage />)
    expect(screen.getByText(/^adminNamespaces.confirm.remove.description:.*Platform Tools/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'dialog.confirm' }))

    await waitFor(() => expect(mockState.remove).toHaveBeenCalledWith({
      slug: 'platform-tools',
      userId: 'admin',
    }))
  })

  it('keeps a lifecycle mutation bound to its captured namespace target', async () => {
    const { rerender } = render(<AdminNamespacesPage />)
    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.actions.freeze' }))
    mockState.listItems = [{ ...summary, id: 9, slug: 'new-first', displayName: 'New First' }, summary]
    rerender(<AdminNamespacesPage />)
    fireEvent.click(screen.getByRole('button', { name: 'dialog.confirm' }))

    await waitFor(() => expect(mockState.freeze).toHaveBeenCalledWith({
      slug: 'platform-tools',
      reason: undefined,
    }))
  })

  it('pages through every member and applies second-page actions to that member', async () => {
    mockState.memberPages = new Map([
      [0, { items: [ownerMember], total: 150, page: 0, size: 20 }],
      [1, { items: [{ ...adminMember, userId: 'second-page', displayName: 'Second Page Member' }], total: 150, page: 1, size: 20 }],
    ])
    render(<AdminNamespacesPage />)

    expect(screen.getByText(/adminNamespaces.members.total/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.members.next' }))
    expect(screen.getByText('Second Page Member')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.members.remove' }))
    fireEvent.click(screen.getByRole('button', { name: 'dialog.confirm' }))

    await waitFor(() => expect(mockState.remove).toHaveBeenCalledWith({
      slug: 'platform-tools',
      userId: 'second-page',
    }))

    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.members.transfer' }))
    fireEvent.click(screen.getByRole('button', { name: 'dialog.confirm' }))
    await waitFor(() => expect(mockState.transfer).toHaveBeenCalledWith({
      slug: 'platform-tools',
      newOwnerId: 'second-page',
    }))
  })

  it('resets member paging when selecting another namespace', () => {
    mockState.listItems = [summary, { ...summary, id: 2, slug: 'other-team', displayName: 'Other Team' }]
    mockState.memberPages = new Map([
      [0, { items: [ownerMember], total: 150, page: 0, size: 20 }],
      [1, { items: [adminMember], total: 150, page: 1, size: 20 }],
    ])
    render(<AdminNamespacesPage />)
    fireEvent.click(screen.getByRole('button', { name: 'adminNamespaces.members.next' }))
    fireEvent.click(screen.getByRole('button', { name: /Other Team/ }))

    expect(mockState.memberHookCalls[mockState.memberHookCalls.length - 1]).toEqual({ slug: 'other-team', page: 0, size: 20 })
  })

  it('confirms role changes instead of mutating from the select event', async () => {
    render(<AdminNamespacesPage />)
    fireEvent.change(screen.getByLabelText('adminNamespaces.members.changeRole'), { target: { value: 'MEMBER' } })

    expect(mockState.updateRole).not.toHaveBeenCalled()
    expect(screen.getByText('adminNamespaces.confirm.role.title')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'dialog.confirm' }))
    await waitFor(() => expect(mockState.updateRole).toHaveBeenCalledWith({
      slug: 'platform-tools', userId: 'admin', role: 'MEMBER',
    }))
  })

  it('renders translated lifecycle, type, and role labels instead of raw enums', () => {
    const html = renderToStaticMarkup(<AdminNamespacesPage />)
    expect(html).toContain('adminNamespaces.status.ACTIVE')
    expect(html).toContain('adminNamespaces.type.TEAM')
    expect(html).toContain('adminNamespaces.role.OWNER')
    expect(html).not.toContain('>ACTIVE<')
    expect(html).not.toContain('>TEAM<')
    expect(html).not.toContain('>OWNER<')
  })
})

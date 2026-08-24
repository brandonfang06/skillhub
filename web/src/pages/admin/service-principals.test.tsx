/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  createToken: vi.fn(),
  refetchTokens: vi.fn(),
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: { language: 'en' },
    }),
  }
})

vi.mock('@/shared/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/features/admin/service-principals', () => ({
  useServicePrincipals: () => ({
    data: {
      items: [{
        id: 'svc_1',
        code: 'gitlab-importer',
        displayName: 'GitLab Importer',
        status: 'ACTIVE',
        activeTokenCount: 0,
        nearestTokenExpiry: null,
        lastUsedAt: null,
        createdAt: '2026-08-24T00:00:00Z',
        updatedAt: '2026-08-24T00:00:00Z',
      }],
      total: 1,
    },
  }),
  useServiceTokens: () => ({ data: { items: [] }, refetch: mocks.refetchTokens }),
  useServicePrincipalMutations: () => ({
    createPrincipal: { mutateAsync: vi.fn(), isPending: false },
    updatePrincipal: { mutateAsync: vi.fn(), isPending: false },
    createToken: { mutateAsync: mocks.createToken, isPending: false },
    rotateToken: { mutateAsync: vi.fn(), isPending: false },
    revokeToken: { mutateAsync: vi.fn(), isPending: false },
  }),
}))

import { ServicePrincipalsPage } from './service-principals'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ServicePrincipalsPage', () => {
  it('renders translated create-principal dialog actions instead of missing common keys', () => {
    render(<ServicePrincipalsPage />)
    fireEvent.click(screen.getByRole('button', { name: 'servicePrincipals.create' }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('button', { name: 'dialog.cancel' })).toBeTruthy()
    expect(within(dialog).getByRole('button', { name: 'servicePrincipals.create' })).toBeTruthy()
    expect(within(dialog).queryByText('common.cancel')).toBeNull()
    expect(within(dialog).queryByText('common.create')).toBeNull()
  })

  it('submits explicit null only after the admin selects never expires', async () => {
    mocks.createToken.mockResolvedValue({ token: 'st_secret' })
    mocks.refetchTokens.mockResolvedValue(undefined)
    render(<ServicePrincipalsPage />)

    fireEvent.click(screen.getByRole('button', { name: 'servicePrincipals.manageTokens' }))
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'servicePrincipals.createToken' }))

    await waitFor(() => {
      expect(mocks.createToken).toHaveBeenCalledWith({
        id: 'svc_1',
        name: 'production',
        scopes: ['source:import'],
        expiresAt: null,
      })
    })
  })
})

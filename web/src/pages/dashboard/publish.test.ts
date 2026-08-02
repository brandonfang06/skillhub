/** @vitest-environment jsdom */
import { createElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const useSearchMock = vi.fn()
const selectRecords: Array<{ value?: string }> = []
const { publishMutationMock, toastErrorMock } = vi.hoisted(() => ({
  publishMutationMock: vi.fn(),
  toastErrorMock: vi.fn(),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useSearch: () => useSearchMock(),
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  }
})

vi.mock('@/features/publish/upload-zone', () => ({
  UploadZone: ({ onFileSelect }: { onFileSelect: (file: File) => void }) =>
    createElement(
      'button',
      { type: 'button', onClick: () => onFileSelect(new File(['skill'], 'skill.zip')) },
      'choose-file',
    ),
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children, ...props }: { children: ReactNode; [key: string]: unknown }) =>
    createElement('button', { type: 'button', ...props }, children),
}))

vi.mock('@/shared/ui/select', () => ({
  Select: ({ children, value }: { children: unknown; value?: string }) => {
    selectRecords.push({ value })
    return children
  },
  SelectContent: ({ children }: { children: unknown }) => children,
  SelectItem: ({ children }: { children: unknown }) => children,
  SelectTrigger: ({ children }: { children: unknown }) => children,
  SelectValue: () => null,
  normalizeSelectValue: (v: string) => v || null,
}))

vi.mock('@/shared/ui/label', () => ({
  Label: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/shared/ui/card', () => ({
  Card: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/shared/hooks/use-skill-queries', () => ({
  usePublishSkill: () => ({ mutateAsync: publishMutationMock, isPending: false }),
}))

vi.mock('@/shared/hooks/use-namespace-queries', () => ({
  useMyNamespaces: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/shared/components/dashboard-page-header', () => ({
  DashboardPageHeader: () => null,
}))

vi.mock('@/shared/lib/toast', () => ({
  toast: { success: vi.fn(), error: toastErrorMock },
}))

vi.mock('@/api/client', () => ({
  ApiError: class ApiError extends Error {
    status: number
    serverMessage?: string
    serverMessageKey?: string

    constructor(message: string, status: number, serverMessage?: string) {
      super(message)
      this.status = status
      this.serverMessage = serverMessage
    }
  },
}))

import { ApiError } from '@/api/client'
import { PublishPage } from './publish'

describe('PublishPage', () => {
  beforeEach(() => {
    selectRecords.length = 0
    publishMutationMock.mockReset()
    toastErrorMock.mockReset()
    useSearchMock.mockReturnValue({
      namespace: '  team-ai  ',
      visibility: 'private',
    })
  })

  it('prefills namespace and visibility from route search params', () => {
    renderToStaticMarkup(createElement(PublishPage))

    expect(selectRecords[0]?.value).toBe('team-ai')
    expect(selectRecords[1]?.value).toBe('PRIVATE')
  })

  it('falls back to public visibility when search params are missing', () => {
    useSearchMock.mockReturnValue({})

    renderToStaticMarkup(createElement(PublishPage))

    expect(selectRecords[0]?.value).toBe('__select_namespace__')
    expect(selectRecords[1]?.value).toBe('PUBLIC')
  })

  it('exports a named component function', () => {
    expect(typeof PublishPage).toBe('function')
  })

  it('does not tell users to increase a rejected version', async () => {
    publishMutationMock.mockRejectedValue(
      new ApiError(
        'Publish failed',
        409,
        'error.skill.publish.rejectedVersionReuse',
      ),
    )

    render(createElement(PublishPage))
    fireEvent.click(screen.getByText('choose-file'))
    fireEvent.click(screen.getByText('publish.confirm'))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        'publish.error',
        'Publish failed',
      )
    })
  })
})

/** @vitest-environment jsdom */
import { createElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const useSearchMock = vi.fn()
const selectRecords: Array<{ value?: string }> = []
const namespacePickerRecords: Array<{ value: string }> = []
const { packageFolderAsZipMock, publishMutationMock, toastErrorMock } = vi.hoisted(() => ({
  packageFolderAsZipMock: vi.fn(),
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
  UploadZone: ({
    onFileSelect,
    onFolderSelect,
    disabled,
  }: {
    onFileSelect: (file: File) => void
    onFolderSelect?: (files: File[]) => void
    disabled?: boolean
  }) =>
    createElement(
      'div',
      null,
      createElement(
        'button',
        {
          type: 'button',
          disabled,
          onClick: () => onFileSelect(new File(['skill'], 'skill.zip')),
        },
        'choose-file',
      ),
      createElement(
        'button',
        {
          type: 'button',
          disabled,
          onClick: () => onFolderSelect?.([new File(['skill'], 'SKILL.md')]),
        },
        'choose-folder',
      ),
    ),
}))

vi.mock('@/features/publish/folder-zip', async () => {
  const actual = await vi.importActual<typeof import('@/features/publish/folder-zip')>(
    '@/features/publish/folder-zip',
  )
  return {
    ...actual,
    packageFolderAsZip: packageFolderAsZipMock,
  }
})

vi.mock('@/features/publish/namespace-picker', () => ({
  NamespacePicker: ({
    value,
    onValueChange,
  }: {
    value: string
    onValueChange: (value: string) => void
  }) => {
    namespacePickerRecords.push({ value })
    return createElement(
      'button',
      { type: 'button', onClick: () => onValueChange('team-search') },
      'pick-namespace',
    )
  },
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
import { FolderPackagingError } from '@/features/publish/folder-zip'
import { PublishPage } from './publish'

afterEach(cleanup)

describe('PublishPage', () => {
  beforeEach(() => {
    selectRecords.length = 0
    namespacePickerRecords.length = 0
    packageFolderAsZipMock.mockReset()
    publishMutationMock.mockReset()
    toastErrorMock.mockReset()
    useSearchMock.mockReturnValue({
      namespace: '  team-ai  ',
      visibility: 'private',
    })
  })

  it('prefills namespace and visibility from route search params', () => {
    renderToStaticMarkup(createElement(PublishPage))

    expect(namespacePickerRecords[0]?.value).toBe('team-ai')
    expect(selectRecords[0]?.value).toBe('PRIVATE')
  })

  it('falls back to public visibility when search params are missing', () => {
    useSearchMock.mockReturnValue({})

    renderToStaticMarkup(createElement(PublishPage))

    expect(namespacePickerRecords[0]?.value).toBe('')
    expect(selectRecords[0]?.value).toBe('PUBLIC')
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

  it('publishes with the namespace selected by the searchable picker', async () => {
    useSearchMock.mockReturnValue({})
    publishMutationMock.mockResolvedValue({
      namespace: 'team-search',
      slug: 'test-skill',
      version: '1.0.0',
      status: 'PUBLISHED',
    })

    render(createElement(PublishPage))
    fireEvent.click(screen.getByText('pick-namespace'))
    fireEvent.click(screen.getByText('choose-file'))
    fireEvent.click(screen.getByText('publish.confirm'))

    await waitFor(() => {
      expect(publishMutationMock).toHaveBeenCalledWith(expect.objectContaining({
        namespace: 'team-search',
        visibility: 'PUBLIC',
      }))
    })
  })

  it('packages a selected folder and publishes the resulting ZIP', async () => {
    const packagedFile = new File(['packaged'], 'folder-skill.zip', {
      type: 'application/zip',
    })
    packageFolderAsZipMock.mockResolvedValue(packagedFile)
    publishMutationMock.mockResolvedValue({
      namespace: 'team-ai',
      slug: 'folder-skill',
      version: '1.0.0',
      status: 'PENDING_REVIEW',
    })

    render(createElement(PublishPage))
    fireEvent.click(screen.getByText('choose-folder'))
    await screen.findByText(/folder-skill\.zip/)
    fireEvent.click(screen.getByText('publish.confirm'))

    await waitFor(() => {
      expect(packageFolderAsZipMock).toHaveBeenCalledTimes(1)
      expect(publishMutationMock).toHaveBeenCalledWith(expect.objectContaining({
        file: packagedFile,
      }))
    })
  })

  it('shows a specific folder-boundary error and does not publish a stale ZIP', async () => {
    packageFolderAsZipMock.mockRejectedValue(
      new FolderPackagingError('file-too-large', {
        path: 'folder-skill/assets/large.bin',
        limit: 10 * 1024 * 1024,
      }),
    )

    render(createElement(PublishPage))
    fireEvent.click(screen.getByText('choose-file'))
    fireEvent.click(screen.getByText('choose-folder'))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        'publish.folderPackagingErrors.fileTooLarge',
      )
    })
    expect(screen.queryByText(/skill\.zip/)).toBeNull()
    expect(
      (screen.getByText('publish.confirm') as HTMLButtonElement).disabled,
    ).toBe(true)
    expect(publishMutationMock).not.toHaveBeenCalled()
  })
})

/** @vitest-environment jsdom */
import { createElement } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('react-dropzone', () => ({
  useDropzone: () => ({
    getRootProps: () => ({ 'data-testid': 'zip-dropzone' }),
    getInputProps: () => ({ 'aria-label': 'zip-input' }),
    isDragActive: false,
  }),
}))

import { UploadZone } from './upload-zone'

afterEach(cleanup)

describe('UploadZone', () => {
  it('exposes a folder picker only when a folder callback is supplied', () => {
    const { rerender } = render(createElement(UploadZone, { onFileSelect: vi.fn() }))

    expect(screen.queryByText('upload.folderHint')).toBeNull()

    rerender(createElement(UploadZone, {
      onFileSelect: vi.fn(),
      onFolderSelect: vi.fn(),
    }))
    expect(screen.getByText('upload.folderHint')).toBeDefined()
  })

  it('marks the folder input and forwards selected files', () => {
    const onFolderSelect = vi.fn()
    const { container } = render(
      createElement(UploadZone, { onFileSelect: vi.fn(), onFolderSelect }),
    )
    const folderInput = container.querySelector<HTMLInputElement>('input[multiple]')
    expect(folderInput).not.toBeNull()
    expect(folderInput?.hasAttribute('webkitdirectory')).toBe(true)
    expect(folderInput?.hasAttribute('directory')).toBe(true)

    const files = [new File(['skill'], 'SKILL.md')]
    Object.defineProperty(folderInput, 'files', { configurable: true, value: files })
    fireEvent.change(folderInput!)

    expect(onFolderSelect).toHaveBeenCalledWith(files)
    expect(folderInput?.value).toBe('')
  })

  it('disables both ZIP and folder entry points while busy', () => {
    const { container } = render(
      createElement(UploadZone, {
        onFileSelect: vi.fn(),
        onFolderSelect: vi.fn(),
        disabled: true,
      }),
    )

    expect(container.querySelector<HTMLInputElement>('input[multiple]')?.disabled).toBe(true)
    expect(
      (screen.getByRole('button', { name: 'upload.folderHint' }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })
})

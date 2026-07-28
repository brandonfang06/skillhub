import { describe, expect, it } from 'vitest'
import * as module from './import-dialog'
import type {
  RepositoryImportPreview,
  RepositoryImportUpdateCheckResponse,
} from './api'

describe('RepositoryImportDialog', () => {
  it('exports the curator workflow component', () => {
    expect(typeof module.RepositoryImportDialog).toBe('function')
  })

  it('keeps the current preview when SHA is unchanged', () => {
    const current = { importId: 9 } as RepositoryImportPreview
    const check = {
      changed: false,
      preview: null,
    } as RepositoryImportUpdateCheckResponse

    expect(module.previewAfterUpdateCheck(current, check)).toBe(current)
  })

  it('moves to the linked preview only when the SHA changed', () => {
    const current = { importId: 9 } as RepositoryImportPreview
    const next = { importId: 10, previousImportId: 9 } as RepositoryImportPreview
    const check = {
      changed: true,
      preview: next,
    } as RepositoryImportUpdateCheckResponse

    expect(module.previewAfterUpdateCheck(current, check)).toBe(next)
  })
})

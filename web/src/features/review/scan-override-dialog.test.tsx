// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ScanOverrideDialog } from './scan-override-dialog'

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

afterEach(cleanup)

describe('ScanOverrideDialog', () => {
  it('requires explicit confirmation and a trimmed reason before approval', () => {
    const onConfirm = vi.fn()

    render(
      <ScanOverrideDialog
        open
        isPending={false}
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />
    )

    const confirmButton = screen.getByRole('button', { name: 'review.scanOverrideConfirm' })
    expect(confirmButton).toHaveProperty('disabled', true)

    fireEvent.click(screen.getByRole('checkbox', { name: 'review.scanOverrideAcknowledge' }))
    fireEvent.change(screen.getByLabelText('review.scanOverrideReasonLabel'), {
      target: { value: '   ' },
    })
    expect(confirmButton).toHaveProperty('disabled', true)

    fireEvent.change(screen.getByLabelText('review.scanOverrideReasonLabel'), {
      target: { value: ' Provider timeout; static findings reviewed. ' },
    })
    expect(confirmButton).toHaveProperty('disabled', false)
    fireEvent.click(confirmButton)

    expect(onConfirm).toHaveBeenCalledWith('Provider timeout; static findings reviewed.')
  })

  it('disables every action while approval is pending', () => {
    render(
      <ScanOverrideDialog
        open
        isPending
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'review.scanOverrideConfirm' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'dialog.cancel' })).toHaveProperty('disabled', true)
  })
})

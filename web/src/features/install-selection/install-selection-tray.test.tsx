/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number; max?: number }) => (
      `${key}:${options?.count ?? ''}:${options?.max ?? ''}`
    ),
  }),
}))

import { InstallSelectionTray } from './install-selection-tray'

describe('InstallSelectionTray', () => {
  afterEach(() => cleanup())

  it('announces the limit and exposes clear and continue actions', () => {
    const onClear = vi.fn()
    const onContinue = vi.fn()
    render(
      <InstallSelectionTray
        selectedCount={2}
        maxSelected={20}
        onClear={onClear}
        onContinue={onContinue}
      />,
    )

    expect(screen.getByRole('status').textContent).toContain('installSelection.count:2:20')
    fireEvent.click(screen.getByRole('button', { name: 'installSelection.clear::' }))
    fireEvent.click(screen.getByRole('button', { name: 'installSelection.continue::' }))

    expect(onClear).toHaveBeenCalledTimes(1)
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it('disables continue until at least one skill is selected', () => {
    render(
      <InstallSelectionTray
        selectedCount={0}
        maxSelected={20}
        onClear={vi.fn()}
        onContinue={vi.fn()}
      />,
    )

    expect((screen.getByRole('button', { name: 'installSelection.continue::' }) as HTMLButtonElement).disabled).toBe(true)
  })
})

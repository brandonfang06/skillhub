/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  PlaygroundContextDrawer,
  PlaygroundContextPanel,
} from './playground-context'


vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const files = [
  { path: 'SKILL.md', content: 'Primary instructions' },
  { path: 'references/usage.md', content: 'Usage reference' },
]

afterEach(() => cleanup())

function ContextHarness({ drawer = false }: { drawer?: boolean }) {
  const [selectedPath, setSelectedPath] = useState(files[0].path)
  const Component = drawer ? PlaygroundContextDrawer : PlaygroundContextPanel

  return (
    <Component
      files={files}
      selectedPath={selectedPath}
      onSelectedPathChange={setSelectedPath}
    />
  )
}

describe('Playground context browser', () => {
  it('selects files in the read-only desktop panel', () => {
    render(<ContextHarness />)

    expect(screen.getByText('Primary instructions')).toBeTruthy()
    const file = screen.getByRole('button', { name: 'references/usage.md' })
    expect(file.getAttribute('title')).toBe('references/usage.md')
    expect(file.className).toContain('h-11')

    fireEvent.click(file)

    expect(screen.getByText('Usage reference')).toBeTruthy()
    expect(file.getAttribute('aria-pressed')).toBe('true')
  })

  it('opens the same browser in an accessible right-side drawer', () => {
    render(<ContextHarness drawer />)

    fireEvent.click(
      screen.getByRole('button', { name: 'playground.openContext' }),
    )

    expect(
      screen.getByRole('dialog', { name: 'playground.context' }),
    ).toBeTruthy()
    fireEvent.click(
      screen.getByRole('button', { name: 'references/usage.md' }),
    )
    expect(screen.getByText('Usage reference')).toBeTruthy()
  })

  it('returns focus to the trigger after closing the drawer', async () => {
    render(<ContextHarness drawer />)
    const trigger = screen.getByRole('button', {
      name: 'playground.openContext',
    })
    trigger.focus()
    fireEvent.click(trigger)
    fireEvent.click(
      screen.getByRole('button', { name: 'playground.closeContext' }),
    )

    expect(screen.queryByRole('dialog')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })

  it('closes the drawer with Escape', async () => {
    render(<ContextHarness drawer />)
    const trigger = screen.getByRole('button', {
      name: 'playground.openContext',
    })
    trigger.focus()
    fireEvent.click(trigger)
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('dialog')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })
})

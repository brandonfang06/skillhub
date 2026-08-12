/** @vitest-environment jsdom */
import { createElement, type HTMLAttributes, type ReactNode } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ManagedNamespace } from '@/api/types'

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({ t: (key: string) => key }),
  }
})

vi.mock('@/shared/ui/dropdown-menu', async () => {
  const React = await import('react')
  return {
    DropdownMenu: ({ children }: { children: ReactNode }) => children,
    DropdownMenuTrigger: ({ children }: { children: ReactNode }) => children,
    DropdownMenuContent: ({ children }: { children: ReactNode }) => createElement('div', null, children),
    DropdownMenuItem: React.forwardRef<HTMLButtonElement, HTMLAttributes<HTMLButtonElement> & {
      onSelect?: () => void
    }>(({ children, onSelect, ...props }, ref) => createElement(
      'button',
      { ...props, ref, type: 'button', onClick: onSelect },
      children,
    )),
    DropdownMenuSeparator: () => createElement('hr'),
  }
})

import { filterNamespaces, NamespacePicker } from './namespace-picker'

afterEach(cleanup)

function createNamespace(index: number, overrides: Partial<ManagedNamespace> = {}): ManagedNamespace {
  return {
    id: index,
    slug: `team-${index}`,
    displayName: `Team ${index}`,
    type: 'TEAM',
    status: 'ACTIVE',
    createdAt: '2026-08-12T00:00:00Z',
    immutable: false,
    canFreeze: false,
    canUnfreeze: false,
    canArchive: false,
    canRestore: false,
    canDelete: false,
    ...overrides,
  }
}

describe('filterNamespaces', () => {
  const namespaces = Array.from({ length: 125 }, (_, index) => createNamespace(index + 1))

  it('matches display name and slug case-insensitively across large lists', () => {
    const input = [
      ...namespaces,
      createNamespace(200, { displayName: 'AI Platform', slug: 'foundation-models' }),
    ]

    expect(filterNamespaces(input, '  ai PLATFORM ')).toEqual([input[125]])
    expect(filterNamespaces(input, 'FOUNDATION-models')).toEqual([input[125]])
  })

  it('preserves server order and returns the full list for an empty query', () => {
    expect(filterNamespaces(namespaces, '')).toEqual(namespaces)
    expect(filterNamespaces(namespaces, 'team-12').map((namespace) => namespace.slug)).toEqual([
      'team-12',
      'team-120',
      'team-121',
      'team-122',
      'team-123',
      'team-124',
      'team-125',
    ])
  })
})

describe('NamespacePicker', () => {
  const namespaces = [
    createNamespace(1, { displayName: 'AI Platform', slug: 'ai-platform' }),
    createNamespace(2, { displayName: 'Developer Experience', slug: 'devex' }),
  ]

  it('filters visible options and reports an empty result', () => {
    render(createElement(NamespacePicker, {
      namespaces,
      value: '',
      onValueChange: vi.fn(),
      labelId: 'namespace-label',
    }))

    const search = screen.getByRole('searchbox', { name: 'publish.namespaceSearchLabel' })
    fireEvent.change(search, { target: { value: 'devex' } })

    expect(screen.getByText('Developer Experience')).toBeTruthy()
    expect(screen.queryByText('AI Platform')).toBeNull()

    fireEvent.change(search, { target: { value: 'missing' } })
    expect(screen.getByRole('status').textContent).toBe('publish.noMatchingNamespace')
  })

  it('selects and clears a namespace', () => {
    const onValueChange = vi.fn()
    render(createElement(NamespacePicker, {
      namespaces,
      value: 'ai-platform',
      onValueChange,
      labelId: 'namespace-label',
    }))

    expect(document.getElementById('namespace')?.textContent).toContain('AI Platform')
    fireEvent.click(screen.getByText('Developer Experience').closest('button')!)
    expect(onValueChange).toHaveBeenLastCalledWith('devex')

    fireEvent.click(screen.getByRole('button', { name: 'publish.clearNamespace' }))
    expect(onValueChange).toHaveBeenLastCalledWith('')
  })

  it('preserves a route-prefilled slug that is not in the loaded namespace list', () => {
    render(createElement(NamespacePicker, {
      namespaces,
      value: 'prefilled-team',
      onValueChange: vi.fn(),
      labelId: 'namespace-label',
    }))

    expect(document.getElementById('namespace')?.textContent).toContain('@prefilled-team')
  })

  it('moves from the search input to the first or last visible result', () => {
    render(createElement(NamespacePicker, {
      namespaces,
      value: '',
      onValueChange: vi.fn(),
      labelId: 'namespace-label',
    }))

    const search = screen.getByRole('searchbox', { name: 'publish.namespaceSearchLabel' })
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    expect(document.activeElement?.textContent).toContain('AI Platform')

    search.focus()
    fireEvent.keyDown(search, { key: 'ArrowUp' })
    expect(document.activeElement?.textContent).toContain('Developer Experience')

    fireEvent.change(search, { target: { value: 'devex' } })
    fireEvent.keyDown(search, { key: 'ArrowUp' })
    expect(document.activeElement?.textContent).toContain('Developer Experience')
  })
})

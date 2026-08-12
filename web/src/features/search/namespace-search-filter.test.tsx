/** @vitest-environment jsdom */
import { createElement, type HTMLAttributes, type ReactNode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const useNamespacesMock = vi.fn()

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('./use-searchable-namespaces', () => ({
  useSearchableNamespaces: (...args: unknown[]) => useNamespacesMock(...args),
}))
vi.mock('@/shared/ui/dropdown-menu', async () => {
  const React = await import('react')
  return {
    DropdownMenu: ({ children }: { children: ReactNode }) => children,
    DropdownMenuTrigger: ({ children }: { children: ReactNode }) => children,
    DropdownMenuContent: ({ children }: { children: ReactNode }) => createElement('div', { role: 'menu' }, children),
    DropdownMenuItem: React.forwardRef<HTMLButtonElement, HTMLAttributes<HTMLButtonElement> & { onSelect?: () => void }>(
      ({ children, onSelect, ...props }, ref) => createElement('button', { ...props, ref, type: 'button', onClick: onSelect }, children),
    ),
    DropdownMenuSeparator: () => createElement('hr'),
  }
})

import { NamespaceSearchFilter } from './namespace-search-filter'

afterEach(cleanup)

describe('NamespaceSearchFilter', () => {
  it('selects and clears one server-provided namespace', () => {
    useNamespacesMock.mockReturnValue({
      data: [{ slug: 'team-ai', displayName: 'AI Platform', visibleSkillCount: 12 }],
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    })
    const onValueChange = vi.fn()
    render(<NamespaceSearchFilter value="" onValueChange={onValueChange} />)

    fireEvent.click(screen.getByText('AI Platform').closest('button')!)
    expect(onValueChange).toHaveBeenLastCalledWith('team-ai')
    fireEvent.click(screen.getAllByText('search.allNamespaces')[1].closest('button')!)
    expect(onValueChange).toHaveBeenLastCalledWith('')
  })

  it('preserves an unknown selected slug and shows empty and error states', () => {
    useNamespacesMock.mockReturnValue({ data: [], isFetching: false, isError: false, refetch: vi.fn() })
    const { rerender } = render(<NamespaceSearchFilter value="legacy-team" onValueChange={vi.fn()} />)
    expect(screen.getByText('@legacy-team')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('search.noMatchingNamespaces')

    useNamespacesMock.mockReturnValue({ data: [], isFetching: false, isError: true, refetch: vi.fn() })
    rerender(<NamespaceSearchFilter value="legacy-team" onValueChange={vi.fn()} />)
    expect(screen.getByText('search.namespaceLoadError')).toBeTruthy()
  })

  it('debounces namespace input before querying', () => {
    vi.useFakeTimers()
    useNamespacesMock.mockReturnValue({ data: [], isFetching: false, isError: false, refetch: vi.fn() })
    render(<NamespaceSearchFilter value="" onValueChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('search.namespaceSearchLabel'), { target: { value: 'AI' } })
    expect(useNamespacesMock).toHaveBeenLastCalledWith('', false)
    act(() => vi.advanceTimersByTime(250))
    expect(useNamespacesMock).toHaveBeenLastCalledWith('AI', false)
    vi.useRealTimers()
  })

  it('moves from the search input to the first and last result', () => {
    useNamespacesMock.mockReturnValue({
      data: [
        { slug: 'team-a', displayName: 'Team A', visibleSkillCount: 2 },
        { slug: 'team-z', displayName: 'Team Z', visibleSkillCount: 1 },
      ],
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    })
    render(<NamespaceSearchFilter value="" onValueChange={vi.fn()} />)
    const input = screen.getByLabelText('search.namespaceSearchLabel')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(document.activeElement?.textContent).toContain('Team A')
    input.focus()
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(document.activeElement?.textContent).toContain('Team Z')
  })
})

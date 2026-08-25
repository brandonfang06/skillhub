/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigateMock = vi.fn()
const copyMock = vi.fn().mockResolvedValue(undefined)

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { skill?: string; count?: number; max?: number }) => {
      if (options?.skill) return `${key}:${options.skill}`
      if (typeof options?.count === 'number') return `${key}:${options.count}:${options.max ?? ''}`
      return key
    },
  }),
}))

vi.mock('@/shared/lib/runtime-config', () => ({
  getBrowserAppUrl: () => 'https://skillhub.example.com/skillhub',
  getCliRegistryUrl: () => 'https://skillhub.example.com/skillhub',
}))

vi.mock('@/shared/lib/clipboard', () => ({
  useCopyToClipboard: () => [false, copyMock] as const,
}))

import { installSelectionStore } from '@/features/install-selection/install-selection-store'
import { InstallSkillsPage } from './install'

describe('InstallSkillsPage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    copyMock.mockClear()
    installSelectionStore.getState().bindOwner(null)
    installSelectionStore.getState().bindOwner('user-1')
  })

  afterEach(() => cleanup())

  it('shows an empty state with one way back to search', () => {
    render(<InstallSkillsPage />)

    expect(screen.getByRole('heading', { name: 'installSkills.title' })).toBeDefined()
    expect(screen.getByText('installSkills.empty')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'installSkills.backToSearch' }))

    expect(navigateMock).toHaveBeenCalledWith({
      to: '/search',
      search: { q: '', sort: 'relevance', page: 0, starredOnly: false },
    })
  })

  it('requires an Agent, then renders sorted commands for one shared target', () => {
    installSelectionStore.getState().addSkill({
      id: 2,
      namespace: 'team-z',
      slug: 'zeta',
      displayName: 'Zeta',
    })
    installSelectionStore.getState().addSkill({
      id: 1,
      namespace: 'global',
      slug: 'alpha',
      displayName: 'Alpha',
    })

    const { container } = render(<InstallSkillsPage />)
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'installSkills.title' }))
    const copyAll = screen.getByRole('button', { name: 'installSkills.copyAll' }) as HTMLButtonElement
    expect(copyAll.disabled).toBe(true)
    expect(container.textContent).toContain('installSkills.selectAgentRequired')

    fireEvent.click(screen.getByRole('checkbox', { name: 'Codex' }))

    const userCommands = [
      'npx @astron-team/skillhub@latest install alpha --registry https://skillhub.example.com/skillhub --scope user --agent codex',
      'npx @astron-team/skillhub@latest install zeta --namespace team-z --registry https://skillhub.example.com/skillhub --scope user --agent codex',
    ]
    expect(container.textContent).toContain(userCommands[0])
    expect(container.textContent).toContain(userCommands[1])
    expect(copyAll.disabled).toBe(false)

    fireEvent.click(copyAll)
    expect(copyMock).toHaveBeenCalledWith(userCommands.join('\n'))
  })

  it('applies project scope and force to every command with an overwrite warning', () => {
    installSelectionStore.getState().addSkill({
      id: 1,
      namespace: 'global',
      slug: 'alpha',
      displayName: 'Alpha',
    })
    const { container } = render(<InstallSkillsPage />)

    fireEvent.click(screen.getByRole('radio', { name: 'installSkills.scopeProject' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Codex' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'installSkills.forceLabel' }))

    expect(container.textContent).toContain('installSkills.projectWarning')
    expect(container.textContent).toContain('installSkills.forceWarning')
    expect(container.textContent).toContain(
      'install alpha --registry https://skillhub.example.com/skillhub --scope project --agent codex --force',
    )
  })

  it('removes a selected skill and keeps CLI identity guidance visible', () => {
    installSelectionStore.getState().addSkill({
      id: 1,
      namespace: 'global',
      slug: 'alpha',
      displayName: 'Alpha',
    })
    const { container } = render(<InstallSkillsPage />)

    expect(container.textContent).toContain(
      'npx @astron-team/skillhub@latest whoami --registry https://skillhub.example.com/skillhub',
    )
    fireEvent.click(screen.getByRole('button', { name: 'installSkills.removeSkill:Alpha' }))

    expect(installSelectionStore.getState().selectedSkills).toEqual([])
    expect(screen.getByText('installSkills.empty')).toBeDefined()
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'installSkills.title' }))
  })
})

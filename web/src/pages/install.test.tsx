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

  it('requires one Agent, then copies sorted commands with force already enabled', () => {
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

    fireEvent.change(screen.getByLabelText('installSkills.agentsHeading'), {
      target: { value: 'codex' },
    })

    const userCommands = [
      'npx @astron-team/skillhub@latest install alpha --registry https://skillhub.example.com/skillhub --scope user --agent codex --force',
      'npx @astron-team/skillhub@latest install zeta --namespace team-z --registry https://skillhub.example.com/skillhub --scope user --agent codex --force',
    ]
    expect(container.textContent).toContain(userCommands[0])
    expect(container.textContent).toContain(userCommands[1])
    expect(copyAll.disabled).toBe(false)

    fireEvent.click(copyAll)
    expect(copyMock).toHaveBeenCalledWith(userCommands.join('\n'))
  })

  it('puts targets first, commands second, and selected Skills in an open three-row disclosure', () => {
    installSelectionStore.getState().addSkill({
      id: 1,
      namespace: 'global',
      slug: 'alpha',
      displayName: 'Alpha',
    })
    installSelectionStore.getState().addSkill({ id: 2, namespace: 'global', slug: 'beta', displayName: 'Beta' })
    installSelectionStore.getState().addSkill({ id: 3, namespace: 'global', slug: 'gamma', displayName: 'Gamma' })
    installSelectionStore.getState().addSkill({ id: 4, namespace: 'global', slug: 'omega', displayName: 'Omega' })
    const { container } = render(<InstallSkillsPage />)

    const targets = screen.getByRole('heading', { name: 'installSkills.targetsHeading' })
    const commands = screen.getByRole('heading', { name: 'installSkills.commandsHeading' })
    const selected = container.querySelector('details')

    expect(targets.compareDocumentPosition(commands) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(commands.compareDocumentPosition(selected!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(selected?.hasAttribute('open')).toBe(true)
    expect(selected?.querySelector('[data-visible-skill-rows="3"]')).not.toBeNull()
    expect(screen.queryByRole('checkbox', { name: 'installSkills.forceLabel' })).toBeNull()
    expect(container.textContent).not.toContain('installSkills.identityHeading')
    expect(container.textContent).not.toContain('whoami')
  })

  it('applies project scope and removes a Skill from the compact disclosure', () => {
    installSelectionStore.getState().addSkill({
      id: 1,
      namespace: 'global',
      slug: 'alpha',
      displayName: 'Alpha',
    })
    const { container } = render(<InstallSkillsPage />)

    fireEvent.change(screen.getByLabelText('installSkills.agentsHeading'), {
      target: { value: 'codex' },
    })
    fireEvent.click(screen.getByRole('radio', { name: 'installSkills.scopeProject' }))

    expect(container.textContent).toContain('installSkills.projectWarning')
    expect(container.textContent).toContain(
      'install alpha --registry https://skillhub.example.com/skillhub --scope project --agent codex --force',
    )

    fireEvent.click(screen.getByRole('button', { name: 'installSkills.removeSkill:Alpha' }))

    expect(installSelectionStore.getState().selectedSkills).toEqual([])
    expect(screen.getByText('installSkills.empty')).toBeDefined()
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'installSkills.title' }))
  })
})

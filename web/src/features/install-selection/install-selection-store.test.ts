import { describe, expect, it } from 'vitest'
import {
  INSTALL_SELECTION_STORAGE_KEY,
  MAX_SELECTED_SKILLS,
  createInstallSelectionStore,
} from './install-selection-store'

describe('install selection store', () => {
  it('keeps one canonical entry per skill in stable namespace and slug order', () => {
    const store = createInstallSelectionStore()
    const beta = {
      id: 2,
      namespace: 'team-b',
      slug: 'zeta',
      displayName: 'Zeta',
    }
    const alpha = {
      id: 1,
      namespace: 'team-a',
      slug: 'alpha',
      displayName: 'Alpha',
    }

    store.getState().bindOwner('user-a')
    store.getState().enterSelectionMode()
    store.getState().addSkill(beta)
    store.getState().addSkill(alpha)
    store.getState().addSkill({ ...alpha, id: 99, displayName: 'Duplicate Alpha' })

    expect(store.getState().selectedSkills).toEqual([alpha, beta])
    expect(store.getState().isSelectionMode).toBe(true)
  })

  it('rejects additions beyond the shared selection limit', () => {
    const store = createInstallSelectionStore()
    store.getState().bindOwner('user-a')

    for (let index = 0; index <= MAX_SELECTED_SKILLS; index += 1) {
      store.getState().addSkill({
        id: index,
        namespace: 'global',
        slug: `skill-${index.toString().padStart(2, '0')}`,
        displayName: `Skill ${index}`,
      })
    }

    expect(store.getState().selectedSkills).toHaveLength(MAX_SELECTED_SKILLS)
    expect(store.getState().selectedSkills.some((skill) => skill.slug === 'skill-20')).toBe(false)
  })

  it('removes and clears selected skills without retaining selection mode', () => {
    const store = createInstallSelectionStore()
    const alpha = {
      id: 1,
      namespace: 'global',
      slug: 'alpha',
      displayName: 'Alpha',
    }
    const beta = {
      id: 2,
      namespace: 'global',
      slug: 'beta',
      displayName: 'Beta',
    }
    store.getState().bindOwner('user-a')
    store.getState().enterSelectionMode()

    store.getState().addSkill(beta)
    store.getState().removeSkill(beta)
    store.getState().addSkill(alpha)
    store.getState().clearSelection()

    expect(store.getState().selectedSkills).toEqual([])
    expect(store.getState().isSelectionMode).toBe(false)
  })

  it('rehydrates tab options and resets all workflow state for a different user', () => {
    const values = new Map<string, string>()
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    }
    const firstStore = createInstallSelectionStore(storage)
    firstStore.getState().bindOwner('user-a')
    firstStore.getState().enterSelectionMode()
    firstStore.getState().addSkill({
      id: 1,
      namespace: 'global',
      slug: 'alpha',
      displayName: 'Alpha',
    })
    firstStore.getState().setScope('project')
    firstStore.getState().setAgent('codex')
    firstStore.getState().setTargetMode('interactive')

    const restoredStore = createInstallSelectionStore(storage)

    expect(restoredStore.getState()).toMatchObject({
      ownerUserId: null,
      isSelectionMode: false,
      selectedSkills: [],
      scope: 'user',
      selectedAgentId: null,
      targetMode: 'direct',
    })

    restoredStore.getState().bindOwner('user-a')

    expect(restoredStore.getState()).toMatchObject({
      ownerUserId: 'user-a',
      isSelectionMode: true,
      scope: 'project',
      selectedAgentId: 'codex',
      targetMode: 'interactive',
    })
    expect(restoredStore.getState().selectedSkills).toHaveLength(1)

    restoredStore.getState().bindOwner('user-b')

    expect(restoredStore.getState()).toMatchObject({
      ownerUserId: 'user-b',
      isSelectionMode: false,
      selectedSkills: [],
      scope: 'user',
      selectedAgentId: null,
      targetMode: 'direct',
    })
  })

  it('keeps the direct Agent while switching to Terminal-interactive targets', () => {
    const store = createInstallSelectionStore()
    store.getState().bindOwner('user-a')
    store.getState().setAgent('codex')

    store.getState().setTargetMode('interactive')

    expect(store.getState()).toMatchObject({
      selectedAgentId: 'codex',
      targetMode: 'interactive',
    })

    store.getState().setTargetMode('direct')

    expect(store.getState()).toMatchObject({
      selectedAgentId: 'codex',
      targetMode: 'direct',
    })
  })

  it('deduplicates canonical coordinates before restoring the selection limit', () => {
    const selectedSkills = [
      { id: 1, namespace: 'Global', slug: 'alpha', displayName: 'Alpha' },
      { id: 2, namespace: 'global', slug: 'ALPHA', displayName: 'Duplicate Alpha' },
      ...Array.from({ length: MAX_SELECTED_SKILLS }, (_, index) => ({
        id: index + 3,
        namespace: 'global',
        slug: `skill-${index.toString().padStart(2, '0')}`,
        displayName: `Skill ${index}`,
      })),
    ]
    const values = new Map<string, string>([[
      INSTALL_SELECTION_STORAGE_KEY,
      JSON.stringify({
        version: 2,
        state: {
          ownerUserId: 'user-a',
          isSelectionMode: true,
          selectedSkills,
          scope: 'user',
          selectedAgentId: 'codex',
        },
      }),
    ]])
    const store = createInstallSelectionStore({
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    })

    store.getState().bindOwner('user-a')

    expect(store.getState().selectedSkills).toHaveLength(MAX_SELECTED_SKILLS)
    expect(store.getState().selectedSkills.filter((skill) => (
      skill.namespace.toLowerCase() === 'global' && skill.slug.toLowerCase() === 'alpha'
    ))).toHaveLength(1)
    expect(store.getState().selectedSkills.some((skill) => skill.slug === 'skill-18')).toBe(true)
    expect(store.getState().selectedSkills.some((skill) => skill.slug === 'skill-19')).toBe(false)
  })

  it('migrates old multi-Agent state to the first supported Agent in detector order', () => {
    const values = new Map<string, string>([[
      INSTALL_SELECTION_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        state: {
          ownerUserId: 'user-a',
          isSelectionMode: true,
          selectedSkills: [],
          scope: 'user',
          selectedAgentIds: ['generic', 'cursor', 'codex', 'unsupported'],
          force: false,
        },
      }),
    ]])
    const store = createInstallSelectionStore({
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    })

    store.getState().bindOwner('user-a')

    expect(store.getState().selectedAgentId).toBe('codex')

    store.getState().setAgent('cursor')
    expect(store.getState().selectedAgentId).toBe('cursor')

    store.getState().setAgent('generic')
    expect(store.getState().selectedAgentId).toBe('cursor')

    store.getState().setAgent(null)
    expect(store.getState().selectedAgentId).toBeNull()
  })
})

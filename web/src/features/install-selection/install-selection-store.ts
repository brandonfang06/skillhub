import { createStore } from 'zustand/vanilla'
import { useStore } from 'zustand'
import { normalizeInstallAgentIds } from './install-agents'

export const MAX_SELECTED_SKILLS = 20
export const INSTALL_SELECTION_STORAGE_KEY = 'skillhub.install-selection.v1'

export type InstallScope = 'user' | 'project'

export interface InstallSelectionStorage {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
  removeItem: (key: string) => void
}

export interface InstallSelectionSkill {
  id: number
  namespace: string
  slug: string
  displayName: string
}

export interface InstallSelectionState {
  ownerUserId: string | null
  isSelectionMode: boolean
  selectedSkills: InstallSelectionSkill[]
  scope: InstallScope
  selectedAgentIds: string[]
  force: boolean
  bindOwner: (userId: string | null) => void
  enterSelectionMode: () => void
  addSkill: (skill: InstallSelectionSkill) => void
  removeSkill: (skill: Pick<InstallSelectionSkill, 'namespace' | 'slug'>) => void
  clearSelection: () => void
  setScope: (scope: InstallScope) => void
  toggleAgent: (agentId: string) => void
  setForce: (force: boolean) => void
}

type PersistedInstallSelectionState = Pick<
  InstallSelectionState,
  'ownerUserId' | 'isSelectionMode' | 'selectedSkills' | 'scope' | 'selectedAgentIds' | 'force'
>

interface PersistedInstallSelectionEnvelope {
  version: 1
  state: PersistedInstallSelectionState
}

export function installSelectionSkillCoordinate(
  skill: Pick<InstallSelectionSkill, 'namespace' | 'slug'>,
): string {
  return `${skill.namespace}/${skill.slug}`.toLowerCase()
}

function compareSkills(left: InstallSelectionSkill, right: InstallSelectionSkill): number {
  const leftCoordinate = installSelectionSkillCoordinate(left)
  const rightCoordinate = installSelectionSkillCoordinate(right)
  if (leftCoordinate < rightCoordinate) return -1
  if (leftCoordinate > rightCoordinate) return 1
  return 0
}

function defaultState(ownerUserId: string | null = null): PersistedInstallSelectionState {
  return {
    ownerUserId,
    isSelectionMode: false,
    selectedSkills: [],
    scope: 'user',
    selectedAgentIds: [],
    force: false,
  }
}

function isInstallSelectionSkill(value: unknown): value is InstallSelectionSkill {
  if (!value || typeof value !== 'object') return false
  const skill = value as Partial<InstallSelectionSkill>
  return typeof skill.id === 'number'
    && typeof skill.namespace === 'string'
    && typeof skill.slug === 'string'
    && typeof skill.displayName === 'string'
}

function normalizeSelectedSkills(values: unknown[]): InstallSelectionSkill[] {
  const uniqueSkills = new Map<string, InstallSelectionSkill>()
  for (const value of values) {
    if (!isInstallSelectionSkill(value)) continue
    const coordinate = installSelectionSkillCoordinate(value)
    if (!uniqueSkills.has(coordinate)) {
      uniqueSkills.set(coordinate, value)
    }
  }
  return [...uniqueSkills.values()]
    .sort(compareSkills)
    .slice(0, MAX_SELECTED_SKILLS)
}

function readPersistedState(storage?: InstallSelectionStorage): PersistedInstallSelectionState {
  if (!storage) return defaultState()
  try {
    const rawValue = storage.getItem(INSTALL_SELECTION_STORAGE_KEY)
    if (!rawValue) return defaultState()
    const envelope = JSON.parse(rawValue) as Partial<PersistedInstallSelectionEnvelope>
    if (envelope.version !== 1 || !envelope.state || typeof envelope.state !== 'object') {
      storage.removeItem(INSTALL_SELECTION_STORAGE_KEY)
      return defaultState()
    }
    const state = envelope.state as Partial<PersistedInstallSelectionState>
    const ownerUserId = typeof state.ownerUserId === 'string' ? state.ownerUserId : null
    const selectedSkills = Array.isArray(state.selectedSkills)
      ? normalizeSelectedSkills(state.selectedSkills)
      : []
    const selectedAgentIds = Array.isArray(state.selectedAgentIds)
      ? normalizeInstallAgentIds(state.selectedAgentIds.filter((value): value is string => typeof value === 'string'))
      : []
    return {
      ownerUserId,
      isSelectionMode: ownerUserId !== null && state.isSelectionMode === true,
      selectedSkills: ownerUserId === null ? [] : selectedSkills,
      scope: state.scope === 'project' ? 'project' : 'user',
      selectedAgentIds: ownerUserId === null ? [] : selectedAgentIds,
      force: ownerUserId !== null && state.force === true,
    }
  } catch {
    storage.removeItem(INSTALL_SELECTION_STORAGE_KEY)
    return defaultState()
  }
}

function writePersistedState(storage: InstallSelectionStorage, state: InstallSelectionState): void {
  const envelope: PersistedInstallSelectionEnvelope = {
    version: 1,
    state: {
      ownerUserId: state.ownerUserId,
      isSelectionMode: state.isSelectionMode,
      selectedSkills: state.selectedSkills,
      scope: state.scope,
      selectedAgentIds: state.selectedAgentIds,
      force: state.force,
    },
  }
  storage.setItem(INSTALL_SELECTION_STORAGE_KEY, JSON.stringify(envelope))
}

export function createInstallSelectionStore(storage?: InstallSelectionStorage) {
  let pendingPersistedState: PersistedInstallSelectionState | null = readPersistedState(storage)
  const store = createStore<InstallSelectionState>((set) => ({
    ...defaultState(),
    bindOwner: (userId) => set((state) => {
      const persistedState = pendingPersistedState
      pendingPersistedState = null
      if (userId !== null && persistedState?.ownerUserId === userId) {
        return persistedState
      }
      if (state.ownerUserId === userId) return state
      return defaultState(userId)
    }),
    enterSelectionMode: () => set((state) => (
      state.ownerUserId ? { isSelectionMode: true } : state
    )),
    addSkill: (skill) => set((state) => {
      if (!state.ownerUserId) return state
      const coordinate = installSelectionSkillCoordinate(skill)
      if (
        state.selectedSkills.length >= MAX_SELECTED_SKILLS
        || state.selectedSkills.some((item) => installSelectionSkillCoordinate(item) === coordinate)
      ) {
        return state
      }
      return {
        selectedSkills: [...state.selectedSkills, skill].sort(compareSkills),
      }
    }),
    removeSkill: (skill) => set((state) => {
      const coordinate = installSelectionSkillCoordinate(skill)
      return {
        selectedSkills: state.selectedSkills.filter((item) => (
          installSelectionSkillCoordinate(item) !== coordinate
        )),
      }
    }),
    clearSelection: () => set({
      isSelectionMode: false,
      selectedSkills: [],
    }),
    setScope: (scope) => set({ scope }),
    toggleAgent: (agentId) => set((state) => {
      if (normalizeInstallAgentIds([agentId]).length === 0) return state
      return {
        selectedAgentIds: state.selectedAgentIds.includes(agentId)
          ? state.selectedAgentIds.filter((value) => value !== agentId)
          : normalizeInstallAgentIds([...state.selectedAgentIds, agentId]),
      }
    }),
    setForce: (force) => set({ force }),
  }))

  if (storage) {
    store.subscribe((state) => writePersistedState(storage, state))
  }
  return store
}

function getSessionStorage(): InstallSelectionStorage | undefined {
  if (typeof window === 'undefined') return undefined
  try {
    return window.sessionStorage
  } catch {
    return undefined
  }
}

export const installSelectionStore = createInstallSelectionStore(getSessionStorage())

export function useInstallSelectionStore<T>(
  selector: (state: InstallSelectionState) => T,
): T {
  return useStore(installSelectionStore, selector)
}

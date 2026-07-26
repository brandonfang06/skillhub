import { afterEach, describe, expect, mock, test } from 'bun:test'
import { mkdir, mkdtemp, rm, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { AgentCandidate } from '../../../src/agents/types'

interface PromptChoice {
  value: AgentCandidate
}

interface PromptOptions {
  choices?: PromptChoice[]
  onRender?: (this: { cursor?: number }) => void
  format?: (selectedTargets: AgentCandidate[]) => AgentCandidate[]
}

const defaultSelectedTargets = (options: PromptOptions): AgentCandidate[] => options.format?.([]) ?? []
let selectPromptTargets = defaultSelectedTargets

mock.module('prompts', () => ({
  default: (options: PromptOptions) => {
    options.onRender?.call({ cursor: 1 })
    return { selected: selectPromptTargets(options) }
  }
}))

afterEach(() => {
  selectPromptTargets = defaultSelectedTargets
})

const { resolveInstallTargets } = await import('../../../src/agents/resolver')

describe('resolveInstallTargets interactive prompt', () => {
  test('uses the highlighted target when Enter submits an empty multiselect', async () => {
    const detected: AgentCandidate[] = [
      { agent: 'codex', rootDir: '/repo/.codex/skills', scope: 'project', source: 'detected' },
      { agent: 'claude-code', rootDir: '/repo/.claude/skills', scope: 'project', source: 'detected' }
    ]
    const highlighted = detected[1]!

    const targets = await resolveInstallTargets({
      cwd: '/repo',
      agents: [],
      json: false,
      interactive: true,
      detected
    })

    expect(targets).toEqual([highlighted])
  })

  test('allows selecting generic alongside detected user targets', async () => {
    selectPromptTargets = options => options.choices?.map(choice => choice.value) ?? []
    const codex: AgentCandidate = {
      agent: 'codex',
      rootDir: '/home/u/.codex/skills',
      scope: 'user',
      source: 'detected'
    }
    const generic: AgentCandidate = {
      agent: 'generic',
      rootDir: '/home/u/.agents/skills',
      scope: 'user',
      source: 'fallback'
    }

    const targets = await resolveInstallTargets({
      cwd: '/repo',
      home: '/home/u',
      agents: [],
      scope: 'user',
      json: false,
      interactive: true,
      detected: [codex]
    })

    expect(targets).toEqual([codex, generic])
  })

  test('deduplicates missing roots beneath linked parent directories', async () => {
    const home = await mkdtemp(join(tmpdir(), 'skillhub-resolver-home-'))
    const genericParent = join(home, '.agents')
    const codexParent = join(home, '.codex')
    const codex: AgentCandidate = {
      agent: 'codex',
      rootDir: join(codexParent, 'skills'),
      scope: 'user',
      source: 'detected'
    }

    try {
      await mkdir(genericParent)
      await symlink(genericParent, codexParent, process.platform === 'win32' ? 'junction' : 'dir')

      const targets = await resolveInstallTargets({
        cwd: '/repo',
        home,
        agents: [],
        scope: 'user',
        json: false,
        interactive: true,
        detected: [codex]
      })

      expect(targets).toEqual([codex])
    } finally {
      await rm(home, { recursive: true, force: true })
    }
  })

  test('deduplicates missing roots that differ only by case on Windows', async () => {
    if (process.platform !== 'win32') return

    const home = await mkdtemp(join(tmpdir(), 'skillhub-resolver-home-'))
    const codex: AgentCandidate = {
      agent: 'codex',
      rootDir: join(home, '.AGENTS', 'SKILLS'),
      scope: 'user',
      source: 'detected'
    }

    try {
      const targets = await resolveInstallTargets({
        cwd: '/repo',
        home,
        agents: [],
        scope: 'user',
        json: false,
        interactive: true,
        detected: [codex]
      })

      expect(targets).toEqual([codex])
    } finally {
      await rm(home, { recursive: true, force: true })
    }
  })
})

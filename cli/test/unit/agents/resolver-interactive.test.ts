import { describe, expect, mock, test } from 'bun:test'
import type { AgentCandidate } from '../../../src/agents/types'

interface PromptOptions {
  onRender?: (this: { cursor?: number }) => void
  format?: (selectedTargets: AgentCandidate[]) => AgentCandidate[]
}

mock.module('prompts', () => ({
  default: (options: PromptOptions) => {
    options.onRender?.call({ cursor: 1 })
    return { selected: options.format?.([]) ?? [] }
  }
}))

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
})

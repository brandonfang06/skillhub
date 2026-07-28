import { describe, expect, test } from 'bun:test'
import type { AgentCandidate } from '../../../src/agents/types'
import {
  collectionInstallCommand,
  type CollectionCommandDeps,
  type CollectionCommandOptions
} from '../../../src/commands/collection'
import { CliError } from '../../../src/shared/errors'
import { EXIT } from '../../../src/shared/constants'

const target: AgentCandidate = {
  agent: 'codex',
  rootDir: '/tmp/.codex/skills',
  scope: 'project',
  source: 'explicit'
}

function installResult() {
  return {
    collection: {
      namespace: 'opensource',
      slug: 'superpowers',
      version: '1.2.0'
    },
    members: [{
      namespace: 'opensource',
      slug: 'brainstorming',
      version: '4.1.0'
    }],
    installed: [{
      namespace: 'opensource',
      slug: 'brainstorming',
      version: '4.1.0',
      agent: 'codex',
      dir: '/tmp/.codex/skills/brainstorming'
    }]
  }
}

function deps(
  capture: {
    targetCalls: number
    installOptions?: Record<string, unknown>
  }
): CollectionCommandDeps {
  return {
    isTTY: () => false,
    promptScope: async () => 'project',
    getStoredToken: async () => undefined,
    resolveInstallTargets: async () => {
      capture.targetCalls += 1
      return [target]
    },
    installCollection: async (options) => {
      capture.installOptions = options as unknown as Record<string, unknown>
      return installResult()
    }
  }
}

describe('collectionInstallCommand', () => {
  test('requires an explicit SkillHub registry before stores or target resolution', async () => {
    let calls = 0
    try {
      await collectionInstallCommand('@opensource/superpowers', {}, {
        isTTY: () => {
          calls += 1
          return false
        },
        promptScope: async () => 'project',
        getStoredToken: async () => {
          calls += 1
          return undefined
        },
        resolveInstallTargets: async () => {
          calls += 1
          return [target]
        },
        installCollection: async () => {
          calls += 1
          return installResult()
        }
      })
      throw new Error('expected registry failure')
    } catch (error) {
      expect(error).toBeInstanceOf(CliError)
      expect(error).toHaveProperty(
        'message',
        '--registry is required for collection install'
      )
      expect(error).toHaveProperty('exitCode', EXIT.usage)
    }
    expect(calls).toBe(0)
  })

  test('resolves targets once and forwards exact collection options', async () => {
    const capture: {
      targetCalls: number
      installOptions?: Record<string, unknown>
    } = { targetCalls: 0 }
    const options: CollectionCommandOptions = {
      registry: 'https://skillhub.example.test/',
      token: 'token',
      version: '1.2.0',
      agent: ['codex'],
      force: true
    }

    const output = await collectionInstallCommand(
      '@opensource/superpowers',
      options,
      deps(capture)
    )

    expect(capture.targetCalls).toBe(1)
    expect(capture.installOptions).toMatchObject({
      registry: 'https://skillhub.example.test',
      token: 'token',
      namespace: 'opensource',
      slug: 'superpowers',
      version: '1.2.0',
      targets: [target],
      force: true
    })
    expect(output).toContain('Installed collection @opensource/superpowers@1.2.0')
    expect(output).toContain(
      'Installed opensource/brainstorming@4.1.0 -> /tmp/.codex/skills/brainstorming (codex)'
    )
  })

  test('renders deterministic aggregate JSON output', async () => {
    const capture: { targetCalls: number } = { targetCalls: 0 }

    const output = await collectionInstallCommand(
      '@opensource/superpowers',
      {
        registry: 'https://skillhub.example.test',
        json: true
      },
      deps(capture)
    )

    expect(JSON.parse(output)).toEqual({
      ok: true,
      ...installResult()
    })
  })

  test.each([
    { scope: 'team' },
    { scope: 'user', dir: '/tmp/skills' },
    { agent: ['codex'], dir: '/tmp/skills' }
  ] as CollectionCommandOptions[])(
    'validates target options before target resolution',
    async (invalidOptions) => {
      const capture: { targetCalls: number } = { targetCalls: 0 }

      await expect(collectionInstallCommand(
        '@opensource/superpowers',
        {
          ...invalidOptions,
          registry: 'https://skillhub.example.test'
        },
        deps(capture)
      )).rejects.toBeInstanceOf(CliError)

      expect(capture.targetCalls).toBe(0)
    }
  )
})

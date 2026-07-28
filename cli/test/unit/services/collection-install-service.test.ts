import { describe, expect, test } from 'bun:test'
import {
  installCollection,
  type CollectionInstallOptions
} from '../../../src/services/collection-install-service'
import type {
  CollectionResolveResponse,
  SkillHubClient
} from '../../../src/clients/skillhub-client'
import type { InstallPackagesOptions } from '../../../src/services/install-transaction'
import { CliError } from '../../../src/shared/errors'

function manifest(): CollectionResolveResponse {
  return {
    namespace: 'opensource',
    slug: 'superpowers',
    version: '1.2.0',
    versionId: 120,
    members: [{
      namespace: 'opensource',
      slug: 'brainstorming',
      version: '4.1.0',
      versionId: 901,
      fingerprint: `sha256:${'a'.repeat(64)}`,
      downloadUrl:
        '/api/cli/v1/skills/opensource/brainstorming/versions/4.1.0/download'
    }]
  }
}

function options(): CollectionInstallOptions {
  return {
    registry: 'https://skillhub.example.test',
    token: 'token',
    namespace: 'opensource',
    slug: 'superpowers',
    version: '1.2.0',
    targets: [{
      agent: 'codex',
      rootDir: '/tmp/skills',
      scope: 'project',
      source: 'explicit'
    }],
    force: false
  }
}

function clientFor(
  response: CollectionResolveResponse
): Pick<SkillHubClient, 'resolveCollection' | 'download'> {
  return {
    resolveCollection: async () => response,
    download: async () => new Response(new Uint8Array([1, 2, 3]))
  }
}

describe('installCollection', () => {
  test('builds an ordered exact-version package transaction', async () => {
    let transaction: InstallPackagesOptions | undefined
    const response = manifest()

    const result = await installCollection(options(), {
      client: clientFor(response),
      installPackages: async (received) => {
        transaction = received
        return {
          installed: [{
            namespace: 'opensource',
            slug: 'brainstorming',
            version: '4.1.0',
            agent: 'codex',
            dir: '/tmp/skills/brainstorming'
          }]
        }
      }
    })

    expect(transaction).toMatchObject({
      registry: 'https://skillhub.example.test',
      force: false,
      collection: {
        namespace: 'opensource',
        slug: 'superpowers',
        version: '1.2.0',
        members: [{
          namespace: 'opensource',
          slug: 'brainstorming',
          version: '4.1.0'
        }]
      }
    })
    expect(transaction?.packages).toHaveLength(1)
    expect(transaction?.packages[0]).toMatchObject({
      namespace: 'opensource',
      slug: 'brainstorming',
      collection: {
        namespace: 'opensource',
        slug: 'superpowers',
        version: '1.2.0'
      }
    })
    expect(result.collection).toEqual({
      namespace: 'opensource',
      slug: 'superpowers',
      version: '1.2.0'
    })
    expect(result.members).toEqual([{
      namespace: 'opensource',
      slug: 'brainstorming',
      version: '4.1.0'
    }])
  })

  test.each([
    {
      name: 'response namespace mismatch',
      mutate: (value: CollectionResolveResponse) => {
        value.namespace = 'other'
      }
    },
    {
      name: 'response slug mismatch',
      mutate: (value: CollectionResolveResponse) => {
        value.slug = 'other'
      }
    },
    {
      name: 'empty members',
      mutate: (value: CollectionResolveResponse) => {
        value.members = []
      }
    },
    {
      name: 'cross-namespace member',
      mutate: (value: CollectionResolveResponse) => {
        value.members[0]!.namespace = 'other'
      }
    },
    {
      name: 'unsafe member slug',
      mutate: (value: CollectionResolveResponse) => {
        value.members[0]!.slug = '../escape'
      }
    },
    {
      name: 'duplicate member',
      mutate: (value: CollectionResolveResponse) => {
        value.members.push({ ...value.members[0]! })
      }
    },
    {
      name: 'more than one hundred members',
      mutate: (value: CollectionResolveResponse) => {
        const member = value.members[0]!
        value.members = Array.from({ length: 101 }, (_, index) => ({
          ...member,
          slug: `skill-${index}`,
          versionId: 1000 + index,
          downloadUrl:
            `/api/cli/v1/skills/opensource/skill-${index}/versions/` +
            `${member.version}/download`
        }))
      }
    },
    {
      name: 'download path mismatch',
      mutate: (value: CollectionResolveResponse) => {
        value.members[0]!.downloadUrl =
          '/api/cli/v1/skills/opensource/brainstorming/versions/latest/download'
      }
    }
  ])('rejects $name before starting the transaction', async ({ mutate }) => {
    const response = manifest()
    mutate(response)
    let transactionCalls = 0

    try {
      await installCollection(options(), {
        client: clientFor(response),
        installPackages: async () => {
          transactionCalls += 1
          return { installed: [] }
        }
      })
      throw new Error('expected validation failure')
    } catch (error) {
      expect(error).toBeInstanceOf(CliError)
      expect(error).toHaveProperty('message', 'invalid collection manifest')
    }
    expect(transactionCalls).toBe(0)
  })
})

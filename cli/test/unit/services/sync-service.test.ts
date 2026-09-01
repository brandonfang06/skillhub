import { describe, expect, test } from 'bun:test'
import { SkillHubClient, type NamespaceSyncResponse } from '../../../src/clients/skillhub-client'
import { listAllNamespaceSkills } from '../../../src/services/sync-service'

describe('namespace sync service', () => {
  test('follows stable manifest cursors until the final page', async () => {
    const cursors: Array<string | undefined> = []
    const pages: NamespaceSyncResponse[] = [
      {
        items: [{
          namespace: 'team-a', slug: 'first', version: '1.0.0', versionId: 1,
          fingerprint: 'sha256:first', updatedAt: '2026-09-01T00:00:00Z',
          visibility: 'NAMESPACE_ONLY', downloadUrl: '/first'
        }],
        nextCursor: '1'
      },
      {
        items: [{
          namespace: 'team-a', slug: 'second', version: '1.0.0', versionId: 2,
          fingerprint: 'sha256:second', updatedAt: '2026-09-01T00:00:00Z',
          visibility: 'NAMESPACE_ONLY', downloadUrl: '/second'
        }],
        nextCursor: null
      }
    ]
    const client = {
      async listNamespaceSkills(_namespace: string, cursor?: string): Promise<NamespaceSyncResponse> {
        cursors.push(cursor)
        return pages.shift()!
      }
    } as unknown as SkillHubClient

    const items = await listAllNamespaceSkills(client, 'team-a')

    expect(cursors).toEqual([undefined, '1'])
    expect(items.map(item => item.slug)).toEqual(['first', 'second'])
  })

  test('rejects a repeated manifest cursor instead of looping forever', async () => {
    let calls = 0
    const client = {
      async listNamespaceSkills(): Promise<NamespaceSyncResponse> {
        calls += 1
        if (calls > 2) throw new Error('unexpected third manifest page')
        return { items: [], nextCursor: '1' }
      }
    } as unknown as SkillHubClient

    await expect(listAllNamespaceSkills(client, 'team-a')).rejects.toThrow(
      'namespace manifest returned a repeated cursor'
    )
    expect(calls).toBe(2)
  })
})

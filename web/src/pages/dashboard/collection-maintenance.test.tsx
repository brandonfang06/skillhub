import { describe, expect, it } from 'vitest'

import {
  buildCollectionDraftInput,
  buildCollectionPublishInput,
  canMaintainCollection,
  partitionDraftMembers,
  removeDegradedDraftMember,
} from './collection-maintenance'

describe('collection maintenance boundaries', () => {
  it('uses backend canCurate as the authoritative UI decision', () => {
    expect(canMaintainCollection({ canCurate: true })).toBe(true)
    expect(canMaintainCollection({ canCurate: false })).toBe(false)
  })

  it('builds a complete ordered draft payload without losing notes', () => {
    expect(
      buildCollectionDraftInput({
        displayName: 'Superpowers',
        summary: 'Workflows',
        releaseNotes: 'Adds testing',
        degradedMembers: [],
        members: [
          {
            skillId: 20,
            skillVersionId: 201,
            skillSlug: 'testing',
            version: '1.0.0',
            position: 4,
            note: 'Run last',
          },
          {
            skillId: 10,
            skillVersionId: 101,
            skillSlug: 'brainstorming',
            version: '2.0.0',
            position: 1,
          },
        ],
      }),
    ).toEqual({
      displayName: 'Superpowers',
      summary: 'Workflows',
      releaseNotes: 'Adds testing',
      members: [
        { skillId: 10, skillVersionId: 101, position: 0 },
        {
          skillId: 20,
          skillVersionId: 201,
          position: 1,
          note: 'Run last',
        },
      ],
    })
  })

  it('requires explicit semver confirmation and current draft revision', () => {
    expect(buildCollectionPublishInput('1.5.0', 7)).toEqual({
      version: '1.5.0',
      draftRevision: 7,
    })
    expect(buildCollectionPublishInput('latest', 7)).toBeNull()
    expect(buildCollectionPublishInput('1.5.0', -1)).toBeNull()
  })

  it('retains degraded snapshots until the curator explicitly removes them', () => {
    const partitioned = partitionDraftMembers([
      {
        skillId: null,
        skillVersionId: null,
        namespace: 'opensource',
        skillSlug: 'deleted-skill',
        version: '1.0.0',
        position: 0,
        note: 'historical pin',
      },
      {
        skillId: 20,
        skillVersionId: 201,
        namespace: 'opensource',
        skillSlug: 'active-skill',
        version: '2.0.0',
        position: 1,
        note: null,
      },
    ])

    expect(partitioned.degradedMembers).toEqual([{
      skillSlug: 'deleted-skill',
      version: '1.0.0',
      position: 0,
      note: 'historical pin',
    }])
    expect(partitioned.members[0].skillId).toBe(20)
    expect(removeDegradedDraftMember(partitioned.degradedMembers, 0)).toEqual([])
  })
})

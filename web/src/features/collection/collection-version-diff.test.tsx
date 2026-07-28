import { describe, expect, it } from 'vitest'

import {
  diffCollectionMembers,
  suggestCollectionVersion,
} from './collection-version-diff'

const member = (
  skillId: number,
  skillVersionId: number,
  skillSlug: string,
  version: string,
  position: number,
) => ({
  skillId,
  skillVersionId,
  skillSlug,
  version,
  position,
})

describe('collection version diff', () => {
  it('classifies additions, removals, changes, and reorder-only edits', () => {
    expect(
      diffCollectionMembers(
        [member(10, 101, 'alpha', '1.0.0', 0)],
        [
          member(10, 101, 'alpha', '1.0.0', 0),
          member(20, 201, 'beta', '1.0.0', 1),
        ],
      ).kind,
    ).toBe('minor')
    expect(
      diffCollectionMembers(
        [
          member(10, 101, 'alpha', '1.0.0', 0),
          member(20, 201, 'beta', '1.0.0', 1),
        ],
        [member(10, 101, 'alpha', '1.0.0', 0)],
      ).kind,
    ).toBe('major')
    expect(
      diffCollectionMembers(
        [member(10, 101, 'alpha', '1.2.3', 0)],
        [member(10, 102, 'alpha', '1.2.4', 0)],
      ).kind,
    ).toBe('patch')
    expect(
      diffCollectionMembers(
        [member(10, 101, 'alpha', '1.2.3', 0)],
        [member(10, 102, 'alpha', '1.3.0', 0)],
      ).kind,
    ).toBe('minor')
    expect(
      diffCollectionMembers(
        [member(10, 101, 'alpha', '1.2.3', 0)],
        [member(10, 102, 'alpha', '2.0.0', 0)],
      ).kind,
    ).toBe('major')
    expect(
      diffCollectionMembers(
        [
          member(10, 101, 'alpha', '1.0.0', 0),
          member(20, 201, 'beta', '1.0.0', 1),
        ],
        [
          member(20, 201, 'beta', '1.0.0', 0),
          member(10, 101, 'alpha', '1.0.0', 1),
        ],
      ).kind,
    ).toBe('patch')
  })

  it('suggests semver without mutating the draft', () => {
    const draft = [member(10, 102, 'alpha', '1.1.0', 0)]
    const diff = diffCollectionMembers(
      [member(10, 101, 'alpha', '1.0.0', 0)],
      draft,
    )

    expect(suggestCollectionVersion('2.4.9', diff)).toBe('2.5.0')
    expect(draft).toEqual([member(10, 102, 'alpha', '1.1.0', 0)])
    expect(suggestCollectionVersion('invalid', diff)).toBeNull()
  })
})

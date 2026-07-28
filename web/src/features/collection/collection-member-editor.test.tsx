// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const { useSkillVersionsByIdMock } = vi.hoisted(() => ({
  useSkillVersionsByIdMock: vi.fn(
    (_skillId: number, _enabled?: boolean) => ({ data: [] }),
  ),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/features/skill/use-skill-versions', () => ({
  useSkillVersions: vi.fn(() => ({ data: [] })),
  useSkillVersionsById: (
    skillId: number,
    enabled?: boolean,
  ) => useSkillVersionsByIdMock(skillId, enabled),
}))

vi.mock('@/shared/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => children,
  SelectContent: ({ children }: { children: React.ReactNode }) => children,
  SelectItem: ({ children }: { children: React.ReactNode }) => children,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => children,
  SelectValue: () => null,
}))

import {
  CollectionMemberEditor,
  DegradedCollectionMemberList,
  addCollectionMember,
  getMemberUpdateSuggestions,
  moveCollectionMember,
  removeCollectionMember,
  updateCollectionMemberNote,
} from './collection-member-editor'

const members = [
  {
    skillId: 10,
    skillVersionId: 101,
    skillSlug: 'alpha',
    version: '1.0.0',
    position: 0,
    note: 'first',
  },
  {
    skillId: 20,
    skillVersionId: 201,
    skillSlug: 'beta',
    version: '2.0.0',
    position: 1,
  },
]

describe('collection member editor helpers', () => {
  it('adds exact immutable IDs and rejects a duplicate Skill ID', () => {
    expect(
      addCollectionMember(members, {
        skillId: 30,
        skillVersionId: 301,
        skillSlug: 'gamma',
        version: '3.0.0',
        note: 'third',
      }),
    ).toEqual([
      ...members,
      {
        skillId: 30,
        skillVersionId: 301,
        skillSlug: 'gamma',
        version: '3.0.0',
        position: 2,
        note: 'third',
      },
    ])
    expect(
      addCollectionMember(members, {
        skillId: 10,
        skillVersionId: 102,
        skillSlug: 'renamed-alpha',
        version: '1.1.0',
      }),
    ).toBeNull()
  })

  it('removes, reorders, and preserves notes with contiguous positions', () => {
    expect(removeCollectionMember(members, 10)).toEqual([
      {
        skillId: 20,
        skillVersionId: 201,
        skillSlug: 'beta',
        version: '2.0.0',
        position: 0,
      },
    ])
    expect(moveCollectionMember(members, 20, -1)).toEqual([
      { ...members[1], position: 0 },
      { ...members[0], position: 1 },
    ])
    expect(updateCollectionMemberNote(members, 10, 'updated')).toEqual([
      { ...members[0], note: 'updated' },
      members[1],
    ])
  })

  it('suggests newer published versions without changing members', () => {
    expect(
      getMemberUpdateSuggestions(members, {
        10: [
          {
            id: 102,
            version: '1.2.0',
            status: 'PUBLISHED',
            downloadAvailable: true,
          },
          {
            id: 103,
            version: '2.0.0',
            status: 'DRAFT',
            downloadAvailable: false,
          },
        ],
        20: [{
          id: 201,
          version: '2.0.0',
          status: 'PUBLISHED',
          downloadAvailable: true,
        }],
      }),
    ).toEqual([{ skillSlug: 'alpha', current: '1.0.0', suggested: '1.2.0' }])
    expect(members[0].version).toBe('1.0.0')
  })

  it('does not suggest a published version until it is download-ready', () => {
    expect(
      getMemberUpdateSuggestions([members[0]], {
        10: [
          {
            id: 103,
            version: '1.2.0',
            status: 'PUBLISHED',
            downloadAvailable: false,
          },
          {
            id: 102,
            version: '1.1.0',
            status: 'PUBLISHED',
            downloadAvailable: true,
          },
        ],
      }),
    ).toEqual([{
      skillSlug: 'alpha',
      current: '1.0.0',
      suggested: '1.1.0',
    }])
  })

  it('loads versions by immutable Skill ID for duplicate coordinates', () => {
    useSkillVersionsByIdMock.mockClear()

    render(
      <CollectionMemberEditor
        namespace="opensource"
        members={[
          members[0],
          {
            ...members[1],
            skillSlug: 'alpha',
          },
        ]}
        skillOptions={[]}
        onChange={vi.fn()}
      />,
    )

    expect(useSkillVersionsByIdMock).toHaveBeenCalledWith(10, true)
    expect(useSkillVersionsByIdMock).toHaveBeenCalledWith(20, true)
  })

  it('renders a degraded snapshot with an explicit repair action', () => {
    const onRemove = vi.fn()

    render(
      <DegradedCollectionMemberList
        members={[{
          skillSlug: 'deleted-skill',
          version: '1.0.0',
          position: 0,
          note: 'historical pin',
        }]}
        onRemove={onRemove}
      />,
    )

    expect(screen.getByText('deleted-skill@1.0.0')).toBeTruthy()
    fireEvent.click(
      screen.getByRole('button', {
        name: 'collectionMaintenance.removeDegradedMember',
      }),
    )
    expect(onRemove).toHaveBeenCalledWith(0)
  })
})

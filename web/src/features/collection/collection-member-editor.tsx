import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'

import type { SkillVersion } from '@/api/types'
import { useSkillVersionsById } from '@/features/skill/use-skill-versions'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'

export interface CollectionSkillOption {
  skillId: number
  slug: string
  displayName: string
}

export interface CollectionEditorMember {
  skillId: number
  skillVersionId: number
  skillSlug: string
  version: string
  position: number
  note?: string | null
}

export interface DegradedCollectionEditorMember {
  skillSlug: string
  version: string
  position: number
  note?: string | null
}

interface VersionCandidate {
  id: number
  version: string
  status: string
  downloadAvailable: boolean
}

function normalizePositions(
  members: CollectionEditorMember[],
): CollectionEditorMember[] {
  return members.map((member, position) => ({ ...member, position }))
}

export function addCollectionMember(
  members: CollectionEditorMember[],
  member: Omit<CollectionEditorMember, 'position'>,
): CollectionEditorMember[] | null {
  if (members.some((current) => current.skillId === member.skillId)) {
    return null
  }
  return [
    ...members,
    {
      ...member,
      position: members.length,
    },
  ]
}

export function removeCollectionMember(
  members: CollectionEditorMember[],
  skillId: number,
): CollectionEditorMember[] {
  return normalizePositions(
    members.filter((member) => member.skillId !== skillId),
  )
}

export function moveCollectionMember(
  members: CollectionEditorMember[],
  skillId: number,
  offset: -1 | 1,
): CollectionEditorMember[] {
  const ordered = [...members].sort((a, b) => a.position - b.position)
  const index = ordered.findIndex((member) => member.skillId === skillId)
  const target = index + offset
  if (index < 0 || target < 0 || target >= ordered.length) return ordered
  const next = [...ordered]
  ;[next[index], next[target]] = [next[target], next[index]]
  return normalizePositions(next)
}

export function updateCollectionMemberNote(
  members: CollectionEditorMember[],
  skillId: number,
  note: string,
): CollectionEditorMember[] {
  return members.map((member) =>
    member.skillId === skillId ? { ...member, note } : member,
  )
}

function versionParts(value: string): number[] {
  const match = /^(\d+)\.(\d+)\.(\d+)/.exec(value)
  return match ? match.slice(1).map(Number) : [0, 0, 0]
}

function compareVersions(a: string, b: string): number {
  const left = versionParts(a)
  const right = versionParts(b)
  for (let index = 0; index < 3; index += 1) {
    if (left[index] !== right[index]) return left[index] - right[index]
  }
  return 0
}

export function getMemberUpdateSuggestions(
  members: CollectionEditorMember[],
  versionsBySkill: Record<number, VersionCandidate[]>,
) {
  return members.flatMap((member) => {
    const latest = versionsBySkill[member.skillId]
      ?.filter(
        (version) =>
          version.status === 'PUBLISHED' && version.downloadAvailable,
      )
      .map((version) => version.version)
      .sort(compareVersions)
      .reverse()[0]
    if (!latest || compareVersions(latest, member.version) <= 0) return []
    return [{
      skillSlug: member.skillSlug,
      current: member.version,
      suggested: latest,
    }]
  })
}

function MemberUpdateSuggestion({
  member,
}: {
  member: CollectionEditorMember
}) {
  const { t } = useTranslation()
  const { data: versions = [] } = useSkillVersionsById(member.skillId, true)
  const suggestion = getMemberUpdateSuggestions(
    [member],
    { [member.skillId]: versions },
  )[0]
  if (!suggestion) return null
  return (
    <p className="mt-2 text-xs text-primary">
      {t('collectionEditor.newerVersion', {
        version: suggestion.suggested,
      })}
    </p>
  )
}

export function DegradedCollectionMemberList({
  members,
  onRemove,
}: {
  members: DegradedCollectionEditorMember[]
  onRemove: (position: number) => void
}) {
  const { t } = useTranslation()
  if (members.length === 0) return null
  return (
    <div
      className="space-y-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4"
      role="alert"
    >
      <p className="text-sm text-destructive">
        {t('collectionMaintenance.degradedDraftHelp')}
      </p>
      <ol className="space-y-2">
        {members
          .slice()
          .sort((a, b) => a.position - b.position)
          .map((member) => (
            <li
              key={`${member.position}:${member.skillSlug}:${member.version}`}
              className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-card p-3"
            >
              <span className="font-mono text-sm">
                {member.skillSlug}@{member.version}
              </span>
              <Button
                className="ml-auto"
                type="button"
                variant="outline"
                onClick={() => onRemove(member.position)}
                aria-label={t(
                  'collectionMaintenance.removeDegradedMember',
                )}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                {t('collectionMaintenance.removeDegradedMember')}
              </Button>
            </li>
          ))}
      </ol>
    </div>
  )
}

export function CollectionMemberEditor({
  namespace,
  members,
  skillOptions,
  onChange,
}: {
  namespace: string
  members: CollectionEditorMember[]
  skillOptions: CollectionSkillOption[]
  onChange: (members: CollectionEditorMember[]) => void
}) {
  const { t } = useTranslation()
  const [skillId, setSkillId] = useState('')
  const [skillVersionId, setSkillVersionId] = useState('')
  const selectedSkill = skillOptions.find(
    (option) => String(option.skillId) === skillId,
  )
  const { data: versions = [] } = useSkillVersionsById(
    selectedSkill?.skillId ?? 0,
    Boolean(selectedSkill),
  )
  const publishedVersions = useMemo(
    () =>
      versions
        .filter(
          (candidate: SkillVersion) =>
            candidate.status === 'PUBLISHED' && candidate.downloadAvailable,
        )
        .sort((a, b) => compareVersions(b.version, a.version)),
    [versions],
  )

  const addMember = () => {
    const selectedVersion = publishedVersions.find(
      (candidate) => String(candidate.id) === skillVersionId,
    )
    if (!selectedSkill || !selectedVersion) return
    const next = addCollectionMember(members, {
      skillId: selectedSkill.skillId,
      skillVersionId: selectedVersion.id,
      skillSlug: selectedSkill.slug,
      version: selectedVersion.version,
    })
    if (next) {
      onChange(next)
      setSkillId('')
      setSkillVersionId('')
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
        <Select
          value={skillId}
          onValueChange={(value) => {
            setSkillId(value)
            setSkillVersionId('')
          }}
        >
          <SelectTrigger aria-label={t('collectionEditor.skill')}>
            <SelectValue placeholder={t('collectionEditor.selectSkill')} />
          </SelectTrigger>
          <SelectContent>
            {skillOptions
              .filter(
                (option) =>
                  !members.some(
                    (member) => member.skillId === option.skillId,
                  ),
              )
              .map((option) => (
                <SelectItem
                  key={option.skillId}
                  value={String(option.skillId)}
                >
                  @{namespace}/{option.slug} — {option.displayName}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
        <Select
          value={skillVersionId}
          onValueChange={setSkillVersionId}
          disabled={!selectedSkill}
        >
          <SelectTrigger aria-label={t('collectionEditor.version')}>
            <SelectValue placeholder={t('collectionEditor.selectVersion')} />
          </SelectTrigger>
          <SelectContent>
            {publishedVersions.map((candidate) => (
              <SelectItem key={candidate.id} value={String(candidate.id)}>
                @{namespace}/{selectedSkill?.slug}@{candidate.version}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          onClick={addMember}
          disabled={!skillId || !skillVersionId}
        >
          <Plus className="mr-2 h-4 w-4" />
          {t('collectionEditor.add')}
        </Button>
      </div>

      <ol className="space-y-3">
        {[...members]
          .sort((a, b) => a.position - b.position)
          .map((member, index) => (
            <li
              key={member.skillVersionId}
              className="rounded-lg border border-border bg-card p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm">
                  {member.skillSlug}@{member.version}
                </span>
                <div className="ml-auto flex gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t('collectionEditor.moveUp')}
                    disabled={index === 0}
                    onClick={() =>
                      onChange(moveCollectionMember(members, member.skillId, -1))
                    }
                  >
                    <ArrowUp className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t('collectionEditor.moveDown')}
                    disabled={index === members.length - 1}
                    onClick={() =>
                      onChange(moveCollectionMember(members, member.skillId, 1))
                    }
                  >
                    <ArrowDown className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t('collectionEditor.remove')}
                    onClick={() =>
                      onChange(removeCollectionMember(members, member.skillId))
                    }
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <Input
                className="mt-3"
                value={member.note ?? ''}
                placeholder={t('collectionEditor.note')}
                onChange={(event) =>
                  onChange(
                    updateCollectionMemberNote(
                      members,
                      member.skillId,
                      event.target.value,
                    ),
                  )
                }
              />
              <MemberUpdateSuggestion
                member={member}
              />
            </li>
          ))}
      </ol>
    </div>
  )
}

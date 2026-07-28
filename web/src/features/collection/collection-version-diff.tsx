import { useTranslation } from 'react-i18next'

import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'

type ChangeKind = 'patch' | 'minor' | 'major'

export interface CollectionDiffMember {
  skillId: number | null
  skillVersionId: number | null
  skillSlug: string
  version: string
  position: number
  note?: string | null
}

export interface ChangedCollectionMember {
  skillId: number | null
  skillSlug: string
  previousVersion: string
  nextVersion: string
  kind: ChangeKind
}

export interface CollectionMemberDiff {
  added: CollectionDiffMember[]
  removed: CollectionDiffMember[]
  changed: ChangedCollectionMember[]
  reordered: boolean
  kind: ChangeKind
}

function parseVersion(value: string): [number, number, number] | null {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(value)
  return match
    ? [Number(match[1]), Number(match[2]), Number(match[3])]
    : null
}

function versionChangeKind(previous: string, next: string): ChangeKind {
  const from = parseVersion(previous)
  const to = parseVersion(next)
  if (!from || !to || from[0] !== to[0]) return 'major'
  if (from[1] !== to[1]) return 'minor'
  return 'patch'
}

function maximumKind(kinds: ChangeKind[]): ChangeKind {
  if (kinds.includes('major')) return 'major'
  if (kinds.includes('minor')) return 'minor'
  return 'patch'
}

export function diffCollectionMembers(
  published: CollectionDiffMember[],
  draft: CollectionDiffMember[],
): CollectionMemberDiff {
  const publishedBySkill = new Map(
    published.map((member) => [member.skillId, member]),
  )
  const draftBySkill = new Map(
    draft.map((member) => [member.skillId, member]),
  )
  const added = draft.filter(
    (member) => !publishedBySkill.has(member.skillId),
  )
  const removed = published.filter(
    (member) => !draftBySkill.has(member.skillId),
  )
  const changed = draft.flatMap((member) => {
    const previous = publishedBySkill.get(member.skillId)
    if (!previous || previous.version === member.version) return []
    return [{
      skillId: member.skillId,
      skillSlug: member.skillSlug,
      previousVersion: previous.version,
      nextVersion: member.version,
      kind: versionChangeKind(previous.version, member.version),
    }]
  })
  const sharedPublishedOrder = published
    .filter((member) => draftBySkill.has(member.skillId))
    .sort((a, b) => a.position - b.position)
    .map((member) => member.skillId)
  const sharedDraftOrder = draft
    .filter((member) => publishedBySkill.has(member.skillId))
    .sort((a, b) => a.position - b.position)
    .map((member) => member.skillId)
  const reordered =
    sharedPublishedOrder.join('\0') !== sharedDraftOrder.join('\0')

  return {
    added,
    removed,
    changed,
    reordered,
    kind: maximumKind([
      ...(removed.length ? ['major' as const] : []),
      ...(added.length ? ['minor' as const] : []),
      ...changed.map((item) => item.kind),
      ...(reordered ? ['patch' as const] : []),
      'patch',
    ]),
  }
}

export function suggestCollectionVersion(
  currentVersion: string,
  diff: CollectionMemberDiff,
): string | null {
  const current = parseVersion(currentVersion)
  if (!current) return null
  if (diff.kind === 'major') return `${current[0] + 1}.0.0`
  if (diff.kind === 'minor') return `${current[0]}.${current[1] + 1}.0`
  return `${current[0]}.${current[1]}.${current[2] + 1}`
}

export function CollectionVersionDiff({
  diff,
}: {
  diff: CollectionMemberDiff
}) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('collectionDiff.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {diff.added.map((member) => (
          <p
            key={`added-${member.skillVersionId ?? `${member.skillSlug}@${member.version}`}`}
            className="text-emerald-700"
          >
            + {member.skillSlug}@{member.version}
          </p>
        ))}
        {diff.removed.map((member) => (
          <p
            key={`removed-${member.skillVersionId ?? `${member.skillSlug}@${member.version}`}`}
            className="text-destructive"
          >
            - {member.skillSlug}@{member.version}
          </p>
        ))}
        {diff.changed.map((member) => (
          <p
            key={`changed-${member.skillId ?? member.skillSlug}`}
            className="text-foreground"
          >
            {member.skillSlug}: {member.previousVersion} → {member.nextVersion}
          </p>
        ))}
        {diff.reordered ? <p>{t('collectionDiff.reordered')}</p> : null}
        {!diff.added.length &&
        !diff.removed.length &&
        !diff.changed.length &&
        !diff.reordered ? (
          <p className="text-muted-foreground">
            {t('collectionDiff.metadataOnly')}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

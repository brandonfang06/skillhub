import { useEffect, useMemo, useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { getCollectionsRuntimeConfig } from '@/api/client'
import {
  CollectionMemberEditor,
  DegradedCollectionMemberList,
  type CollectionEditorMember,
  type DegradedCollectionEditorMember,
} from '@/features/collection/collection-member-editor'
import {
  CollectionVersionDiff,
  diffCollectionMembers,
  suggestCollectionVersion,
} from '@/features/collection/collection-version-diff'
import {
  useCollection,
  useCreateCollectionDraft,
  useDeleteCollectionDraft,
  usePublishCollection,
  useSaveCollectionDraft,
  useSetCollectionStatus,
} from '@/features/collection/use-collections'
import type {
  CollectionDraftInput,
  CollectionMember,
  CollectionPublishInput,
} from '@/features/collection/api'
import { RepositoryImportDialog } from '@/features/repository-import/import-dialog'
import { DashboardPageHeader } from '@/shared/components/dashboard-page-header'
import { EmptyState } from '@/shared/components/empty-state'
import { useSearchSkills } from '@/shared/hooks/use-skill-queries'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import { Textarea } from '@/shared/ui/textarea'

interface DraftFormState {
  displayName: string
  summary: string
  releaseNotes: string
  members: CollectionEditorMember[]
  degradedMembers: DegradedCollectionEditorMember[]
}

export function canMaintainCollection(value: { canCurate: boolean }): boolean {
  return value.canCurate
}

export function buildCollectionDraftInput(
  state: DraftFormState,
): CollectionDraftInput {
  const members = [...state.members]
    .sort((a, b) => a.position - b.position)
    .map((member, position) => ({
      skillId: member.skillId,
      skillVersionId: member.skillVersionId,
      position,
      ...(member.note !== undefined ? { note: member.note } : {}),
    }))
  return {
    displayName: state.displayName.trim(),
    summary: state.summary.trim(),
    releaseNotes: state.releaseNotes.trim() || null,
    members,
  }
}

export function partitionDraftMembers(
  members: CollectionMember[],
): {
  members: CollectionEditorMember[]
  degradedMembers: DegradedCollectionEditorMember[]
} {
  const activeMembers: CollectionEditorMember[] = []
  const degradedMembers: DegradedCollectionEditorMember[] = []
  for (const member of members) {
    if (member.skillId === null || member.skillVersionId === null) {
      degradedMembers.push({
        skillSlug: member.skillSlug,
        version: member.version,
        position: member.position,
        note: member.note,
      })
      continue
    }
    activeMembers.push({
      skillId: member.skillId,
      skillVersionId: member.skillVersionId,
      skillSlug: member.skillSlug,
      version: member.version,
      position: member.position,
      note: member.note,
    })
  }
  return { members: activeMembers, degradedMembers }
}

export function removeDegradedDraftMember(
  members: DegradedCollectionEditorMember[],
  position: number,
): DegradedCollectionEditorMember[] {
  return members.filter((member) => member.position !== position)
}

export function buildCollectionPublishInput(
  version: string,
  draftRevision: number,
): CollectionPublishInput | null {
  if (
    !/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version) ||
    draftRevision < 0
  ) {
    return null
  }
  return { version, draftRevision }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : ''
}

export function CollectionMaintenancePage() {
  const { t } = useTranslation()
  const params = useParams({ strict: false }) as {
    namespace?: string
    collection?: string
  }
  const namespace = params.namespace ?? ''
  const collection = params.collection ?? ''
  const runtime = getCollectionsRuntimeConfig()
  const { data, isLoading } = useCollection(
    namespace,
    collection,
    runtime.enabled,
  )
  const { data: skills } = useSearchSkills({
    namespace,
    page: 0,
    size: 100,
  })
  const createDraft = useCreateCollectionDraft(namespace, collection)
  const saveDraft = useSaveCollectionDraft(namespace, collection)
  const deleteDraft = useDeleteCollectionDraft(namespace, collection)
  const publish = usePublishCollection(namespace, collection)
  const setStatus = useSetCollectionStatus(namespace, collection)
  const [form, setForm] = useState<DraftFormState>({
    displayName: '',
    summary: '',
    releaseNotes: '',
    members: [],
    degradedMembers: [],
  })
  const [publishVersion, setPublishVersion] = useState('')

  useEffect(() => {
    if (!data) return
    const workingVersion = data.draft ?? data.latestPublishedVersion
    const partitioned = partitionDraftMembers(workingVersion?.members ?? [])
    setForm({
      displayName: data.displayName,
      summary: data.summary,
      releaseNotes: workingVersion?.releaseNotes ?? '',
      members: partitioned.members,
      degradedMembers: partitioned.degradedMembers,
    })
  }, [data])

  const diff = useMemo(
    () =>
      diffCollectionMembers(
        data?.latestPublishedVersion?.members.map((member) => ({
          skillId: member.skillId,
          skillVersionId: member.skillVersionId,
          skillSlug: member.skillSlug,
          version: member.version,
          position: member.position,
          note: member.note,
        })) ?? [],
        form.members,
      ),
    [data?.latestPublishedVersion?.members, form.members],
  )
  const suggestedVersion = data?.latestPublishedVersion
    ? suggestCollectionVersion(data.latestPublishedVersion.version, diff)
    : '1.0.0'
  const hasDegradedDraftMember = form.degradedMembers.length > 0
  const serverDraftHasDegradedMember =
    data?.draft?.members.some(
      (member) =>
        member.skillId === null || member.skillVersionId === null,
    ) ?? false

  if (!runtime.enabled) {
    return <EmptyState title={t('collectionAdmin.disabled')} />
  }
  if (isLoading) {
    return <div className="h-48 animate-shimmer rounded-xl" />
  }
  if (!data) {
    return <EmptyState title={t('collectionDetail.notFound')} />
  }
  if (!canMaintainCollection(data)) {
    return <EmptyState title={t('collectionMaintenance.denied')} />
  }

  const run = async (
    action: () => Promise<unknown>,
    successKey: string,
    errorKey: string,
  ) => {
    try {
      await action()
      toast.success(t(successKey))
    } catch (error) {
      toast.error(t(errorKey), errorMessage(error))
    }
  }

  const handleSave = () =>
    run(
      () =>
        saveDraft.mutateAsync({
          input: buildCollectionDraftInput(form),
          draftRevision: data.draft?.draftRevision ?? -1,
        }),
      'collectionMaintenance.saveSuccess',
      'collectionMaintenance.saveError',
    )

  const handlePublish = () => {
    const input = buildCollectionPublishInput(
      publishVersion,
      data.draft?.draftRevision ?? -1,
    )
    if (!input) return
    return run(
      () => publish.mutateAsync(input),
      'collectionMaintenance.publishSuccess',
      'collectionMaintenance.publishError',
    )
  }

  const isPending =
    createDraft.isPending ||
    saveDraft.isPending ||
    deleteDraft.isPending ||
    publish.isPending ||
    setStatus.isPending

  return (
    <div className="space-y-8 animate-fade-up">
      <DashboardPageHeader
        title={t('collectionMaintenance.title')}
        subtitle={`@${namespace}/${collection}`}
      />

      {runtime.gitlabImportEnabled ? (
        <div className="flex justify-end">
          <RepositoryImportDialog
            namespace={namespace}
            collectionSlug={collection}
            collectionDisplayName={form.displayName}
            collectionSummary={form.summary}
          />
        </div>
      ) : null}

      <Card className="space-y-4 p-6">
        <div className="grid gap-4 md:grid-cols-2">
          <Input
            aria-label={t('collectionAdmin.displayName')}
            value={form.displayName}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                displayName: event.target.value,
              }))
            }
            disabled={!data.draft}
          />
          <Input value={`@${namespace}/${collection}`} disabled />
        </div>
        <Textarea
          aria-label={t('collectionAdmin.summary')}
          value={form.summary}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              summary: event.target.value,
            }))
          }
          disabled={!data.draft}
        />
        <Textarea
          aria-label={t('collectionMaintenance.releaseNotes')}
          value={form.releaseNotes}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              releaseNotes: event.target.value,
            }))
          }
          disabled={!data.draft}
        />

        {data.draft ? (
          <div className="space-y-4">
            <DegradedCollectionMemberList
              members={form.degradedMembers}
              onRemove={(position) =>
                setForm((current) => ({
                  ...current,
                  degradedMembers: removeDegradedDraftMember(
                    current.degradedMembers,
                    position,
                  ),
                }))
              }
            />
            <CollectionMemberEditor
              namespace={namespace}
              members={form.members}
              skillOptions={(skills?.items ?? []).map((skill) => ({
                skillId: skill.id,
                slug: skill.slug,
                displayName: skill.displayName,
              }))}
              onChange={(members) =>
                setForm((current) => ({ ...current, members }))
              }
            />
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {!data.draft ? (
            <Button
              disabled={isPending}
              onClick={() =>
                run(
                  () => createDraft.mutateAsync(),
                  'collectionMaintenance.draftCreated',
                  'collectionMaintenance.draftCreateError',
                )
              }
            >
              {t('collectionMaintenance.createDraft')}
            </Button>
          ) : (
            <>
              <Button
                disabled={isPending || hasDegradedDraftMember}
                onClick={handleSave}
              >
                {t('collectionMaintenance.saveDraft')}
              </Button>
              <Button
                variant="outline"
                disabled={isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      t('collectionMaintenance.deleteDraftConfirm'),
                    )
                  ) {
                    void run(
                      () => deleteDraft.mutateAsync(),
                      'collectionMaintenance.deleteSuccess',
                      'collectionMaintenance.deleteError',
                    )
                  }
                }}
              >
                {t('collectionMaintenance.deleteDraft')}
              </Button>
            </>
          )}
          <Button
            variant="outline"
            disabled={isPending}
            onClick={() =>
              run(
                () =>
                  setStatus.mutateAsync({
                    status:
                      data.status === 'ARCHIVED' ? 'ACTIVE' : 'ARCHIVED',
                  }),
                data.status === 'ARCHIVED'
                  ? 'collectionMaintenance.restoreSuccess'
                  : 'collectionMaintenance.archiveSuccess',
                'collectionMaintenance.statusError',
              )
            }
          >
            {data.status === 'ARCHIVED'
              ? t('collectionMaintenance.restore')
              : t('collectionMaintenance.archive')}
          </Button>
        </div>
      </Card>

      {data.draft ? (
        <>
          <CollectionVersionDiff diff={diff} />
          <Card className="space-y-4 p-6">
            <div>
              <h2 className="font-heading text-xl font-semibold">
                {t('collectionMaintenance.publish')}
              </h2>
              <p className="text-sm text-muted-foreground">
                {t('collectionMaintenance.suggestedVersion', {
                  version: suggestedVersion,
                })}
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Input
                value={publishVersion}
                onChange={(event) => setPublishVersion(event.target.value)}
                placeholder={suggestedVersion ?? '1.0.0'}
                aria-label={t('collectionMaintenance.publishVersion')}
              />
              <Button
                disabled={
                  isPending ||
                  hasDegradedDraftMember ||
                  serverDraftHasDegradedMember ||
                  !buildCollectionPublishInput(
                    publishVersion,
                    data.draft.draftRevision,
                  )
                }
                onClick={handlePublish}
              >
                {t('collectionMaintenance.publish')}
              </Button>
            </div>
          </Card>
        </>
      ) : null}
    </div>
  )
}

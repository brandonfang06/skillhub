import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'

import type {
  RepositoryImportIngestResponse,
  RepositoryImportPreview as Preview,
  RepositoryImportSelection,
  RepositoryImportUpdateCheckResponse,
} from './api'
import { RepositoryImportPreview } from './import-preview'
import {
  useIngestRepositoryImport,
  useCheckRepositoryImportUpdates,
  usePreviewRepositoryImport,
  useSeedRepositoryImportCollection,
} from './use-repository-import'

export function previewAfterUpdateCheck(
  current: Preview,
  result: RepositoryImportUpdateCheckResponse,
): Preview {
  return result.changed && result.preview ? result.preview : current
}

export function RepositoryImportDialog({
  namespace,
  collectionSlug,
  collectionDisplayName,
  collectionSummary,
}: {
  namespace: string
  collectionSlug: string
  collectionDisplayName: string
  collectionSummary: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [projectPath, setProjectPath] = useState('')
  const [requestedRef, setRequestedRef] = useState('main')
  const [preview, setPreview] = useState<Preview>()
  const [result, setResult] = useState<RepositoryImportIngestResponse>()
  const [lastSelections, setLastSelections] = useState<
    RepositoryImportSelection[]
  >([])
  const [lastUpdateCheck, setLastUpdateCheck] =
    useState<RepositoryImportUpdateCheckResponse>()
  const previewMutation = usePreviewRepositoryImport(namespace)
  const ingestMutation = useIngestRepositoryImport()
  const updateMutation = useCheckRepositoryImportUpdates()
  const seedMutation = useSeedRepositoryImportCollection(
    namespace,
    collectionSlug,
  )

  const runPreview = async () => {
    try {
      const data = await previewMutation.mutateAsync({
        projectPath: projectPath.trim(),
        ref: requestedRef.trim(),
      })
      setPreview(data)
      setResult(undefined)
      setLastUpdateCheck(undefined)
    } catch (error) {
      toast.error(
        t('repositoryImport.previewError'),
        error instanceof Error ? error.message : '',
      )
    }
  }

  const checkUpdates = async () => {
    if (!preview) return
    try {
      const data = await updateMutation.mutateAsync(preview.importId)
      setLastUpdateCheck(data)
      if (!data.changed || !data.preview) {
        toast.info(t('repositoryImport.noUpdates'))
        return
      }
      setPreview(previewAfterUpdateCheck(preview, data))
      setResult(undefined)
      setLastSelections([])
      toast.info(t('repositoryImport.updateAvailable'))
    } catch (error) {
      toast.error(
        t('repositoryImport.updateError'),
        error instanceof Error ? error.message : '',
      )
    }
  }

  const runIngest = async (selections: RepositoryImportSelection[]) => {
    if (!preview) return
    setLastSelections(selections)
    try {
      const data = await ingestMutation.mutateAsync({
        importId: preview.importId,
        request: { candidates: selections },
      })
      setResult(data)
    } catch (error) {
      toast.error(
        t('repositoryImport.ingestError'),
        error instanceof Error ? error.message : '',
      )
    }
  }

  const seedDraft = async () => {
    if (!preview) return
    const createdIds = new Set(
      result?.results
        .filter((item) => item.state === 'CREATED' && item.versionStatus === 'PUBLISHED')
        .map((item) => item.candidateId) ?? [],
    )
    const candidateIds = lastSelections
      .map((item) => item.candidateId)
      .filter((candidateId) => createdIds.has(candidateId))
    if (candidateIds.length !== lastSelections.length) return
    try {
      await seedMutation.mutateAsync({
        importId: preview.importId,
        request: {
          collectionSlug,
          displayName: collectionDisplayName,
          summary: collectionSummary,
          candidateIds,
        },
      })
      toast.success(t('repositoryImport.seedSuccess'))
      setOpen(false)
    } catch (error) {
      toast.error(
        t('repositoryImport.seedError'),
        error instanceof Error ? error.message : '',
      )
    }
  }

  const canSeed =
    result?.state === 'COMPLETED' &&
    lastSelections.length > 0 &&
    result.results.every(
      (item) =>
        item.state === 'CREATED' && item.versionStatus === 'PUBLISHED',
    )

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          {t('repositoryImport.open')}
        </Button>
      </DialogTrigger>
      <DialogContent className="w-[min(calc(100vw-2rem),56rem)]">
        <DialogHeader>
          <DialogTitle>{t('repositoryImport.title')}</DialogTitle>
          <DialogDescription>
            {t('repositoryImport.description')}
          </DialogDescription>
        </DialogHeader>
        {!preview ? (
          <div className="space-y-4">
            <Input
              value={projectPath}
              onChange={(event) => setProjectPath(event.target.value)}
              placeholder={t('repositoryImport.projectPath')}
              aria-label={t('repositoryImport.projectPath')}
            />
            <Input
              value={requestedRef}
              onChange={(event) => setRequestedRef(event.target.value)}
              placeholder={t('repositoryImport.ref')}
              aria-label={t('repositoryImport.ref')}
            />
            <Button
              disabled={
                previewMutation.isPending ||
                !projectPath.trim() ||
                !requestedRef.trim()
              }
              onClick={runPreview}
            >
              {t('repositoryImport.preview')}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-secondary/50 p-3">
              <div className="text-xs text-muted-foreground">
                {lastUpdateCheck ? (
                  <p>
                    {t('repositoryImport.commitComparison', {
                      previous: lastUpdateCheck.previousCommitSha.slice(0, 8),
                      current: lastUpdateCheck.currentCommitSha.slice(0, 8),
                    })}
                  </p>
                ) : (
                  <p>{t('repositoryImport.manualUpdateOnly')}</p>
                )}
              </div>
              <Button
                type="button"
                variant="outline"
                disabled={updateMutation.isPending}
                onClick={checkUpdates}
              >
                {t('repositoryImport.checkUpdates')}
              </Button>
            </div>
            <RepositoryImportPreview
              preview={preview}
              result={result}
              isPending={ingestMutation.isPending}
              onIngest={runIngest}
            />
            {canSeed ? (
              <Button disabled={seedMutation.isPending} onClick={seedDraft}>
                {t('repositoryImport.seedCollection')}
              </Button>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

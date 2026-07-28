import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'

import type {
  RepositoryImportCandidate,
  RepositoryImportIngestResponse,
  RepositoryImportPreview as Preview,
  RepositoryImportSelection,
} from './api'

export interface CandidateSelectionState {
  selected: boolean
  targetSlug: string
  targetVersion: string
  visibility: 'PUBLIC' | 'NAMESPACE_ONLY' | 'PRIVATE'
}

function safeSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 128)
}

export function buildDefaultCandidateSelection(
  candidate: RepositoryImportCandidate,
): CandidateSelectionState {
  return {
    selected: false,
    targetSlug: safeSlug(candidate.detectedName),
    targetVersion: candidate.sourceVersion || '1.0.0',
    visibility: 'NAMESPACE_ONLY',
  }
}

export function buildIngestSelections(
  candidates: RepositoryImportCandidate[],
  selections: Record<number, CandidateSelectionState>,
): RepositoryImportSelection[] {
  const slugPattern = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/
  const versionPattern = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/
  return candidates.flatMap((candidate) => {
    const selection = selections[candidate.candidateId]
    if (
      !selection?.selected ||
      !slugPattern.test(selection.targetSlug) ||
      selection.targetSlug.includes('--') ||
      !versionPattern.test(selection.targetVersion)
    ) {
      return []
    }
    return [{
      candidateId: candidate.candidateId,
      targetSlug: selection.targetSlug,
      targetVersion: selection.targetVersion,
      visibility: selection.visibility,
    }]
  })
}

export function RepositoryImportPreview({
  preview,
  result,
  isPending,
  onIngest,
}: {
  preview: Preview
  result?: RepositoryImportIngestResponse
  isPending: boolean
  onIngest: (selections: RepositoryImportSelection[]) => void
}) {
  const { t } = useTranslation()
  const [selections, setSelections] = useState<
    Record<number, CandidateSelectionState>
  >({})

  useEffect(() => {
    setSelections(
      Object.fromEntries(
        preview.candidates.map((candidate) => [
          candidate.candidateId,
          buildDefaultCandidateSelection(candidate),
        ]),
      ),
    )
  }, [preview])

  const ingestSelections = useMemo(
    () => buildIngestSelections(preview.candidates, selections),
    [preview.candidates, selections],
  )

  const update = (
    candidateId: number,
    patch: Partial<CandidateSelectionState>,
  ) => {
    setSelections((current) => ({
      ...current,
      [candidateId]: { ...current[candidateId], ...patch },
    }))
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-secondary/50 p-3 text-xs text-muted-foreground">
        <p>{preview.projectFullPath}@{preview.resolvedCommitSha}</p>
        <p>{preview.archiveSha256}</p>
      </div>
      {preview.candidates.map((candidate) => {
        const selection = selections[candidate.candidateId]
        const candidateResult = result?.results.find(
          (item) => item.candidateId === candidate.candidateId,
        )
        return (
          <Card key={candidate.candidateId} className="space-y-3 p-4">
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={selection?.selected ?? false}
                onChange={(event) =>
                  update(candidate.candidateId, {
                    selected: event.target.checked,
                  })
                }
              />
              <span>
                <strong>{candidate.detectedName}</strong>
                <span className="block font-mono text-xs text-muted-foreground">
                  {candidate.sourcePath}
                </span>
              </span>
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              <Input
                aria-label={t('repositoryImport.targetSlug')}
                value={selection?.targetSlug ?? ''}
                onChange={(event) =>
                  update(candidate.candidateId, {
                    targetSlug: event.target.value.toLowerCase(),
                  })
                }
              />
              <Input
                aria-label={t('repositoryImport.targetVersion')}
                value={selection?.targetVersion ?? ''}
                onChange={(event) =>
                  update(candidate.candidateId, {
                    targetVersion: event.target.value,
                  })
                }
              />
              <Select
                value={selection?.visibility ?? 'NAMESPACE_ONLY'}
                onValueChange={(visibility) =>
                  update(candidate.candidateId, {
                    visibility:
                      visibility as CandidateSelectionState['visibility'],
                  })
                }
              >
                <SelectTrigger aria-label={t('repositoryImport.visibility')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="NAMESPACE_ONLY">
                    {t('repositoryImport.namespaceOnly')}
                  </SelectItem>
                  <SelectItem value="PRIVATE">
                    {t('repositoryImport.private')}
                  </SelectItem>
                  <SelectItem value="PUBLIC">
                    {t('repositoryImport.public')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            {(candidate.warnings ?? []).map((warning) => (
              <p key={warning} className="text-xs text-amber-700">
                {warning}
              </p>
            ))}
            {candidateResult ? (
              <p
                className={
                  candidateResult.state === 'CREATED'
                    ? 'text-sm text-emerald-700'
                    : 'text-sm text-destructive'
                }
              >
                {candidateResult.state === 'CREATED'
                  ? t('repositoryImport.created')
                  : t('repositoryImport.failed')}
              </p>
            ) : null}
          </Card>
        )
      })}
      <Button
        disabled={isPending || ingestSelections.length === 0}
        onClick={() => onIngest(ingestSelections)}
      >
        {result?.state === 'PARTIAL'
          ? t('repositoryImport.retry')
          : t('repositoryImport.ingest')}
      </Button>
    </div>
  )
}

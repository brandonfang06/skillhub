import { ChevronDown, FileWarning } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ComplianceMapping, ComplianceSnapshot, SkillVersion } from '@/api/types'
import { cn } from '@/shared/lib/utils'

interface ReviewComplianceDiffPanelProps {
  baseVersion?: SkillVersion | null
  pendingVersion?: SkillVersion | null
  className?: string
}

type DiffKind = 'added' | 'removed' | 'modified'

interface DiffEntry {
  kind: DiffKind
  key: string
  base?: ComplianceMapping
  pending?: ComplianceMapping
}

function normalizedMappingKey(mapping: ComplianceMapping) {
  return [
    mapping.standard?.trim().toLowerCase() ?? '',
    mapping.version?.trim() ?? '',
    mapping.controlId?.trim() ?? '',
  ].join('\u0000')
}

function normalizedEvidenceSignature(mapping: ComplianceMapping) {
  return (mapping.evidence ?? [])
    .map((evidence) => JSON.stringify({
      type: evidence.type?.trim() ?? '',
      path: evidence.path?.trim() ?? '',
      url: evidence.url?.trim() ?? '',
      sha256: evidence.sha256?.trim() ?? '',
    }))
    .sort()
}

function mappingSignature(mapping: ComplianceMapping) {
  return JSON.stringify({
    standard: mapping.standard?.trim().toLowerCase() ?? '',
    version: mapping.version?.trim() ?? '',
    controlId: mapping.controlId?.trim() ?? '',
    title: mapping.title?.trim() ?? '',
    evidence: normalizedEvidenceSignature(mapping),
  })
}

export function compareComplianceSnapshots(
  baseSnapshot?: ComplianceSnapshot | null,
  pendingSnapshot?: ComplianceSnapshot | null,
) {
  const baseItems = new Map(
    (baseSnapshot?.items ?? []).map((item) => [normalizedMappingKey(item), item]),
  )
  const pendingItems = new Map(
    (pendingSnapshot?.items ?? []).map((item) => [normalizedMappingKey(item), item]),
  )
  const keys = new Set([...baseItems.keys(), ...pendingItems.keys()])
  const diffs: DiffEntry[] = []

  for (const key of keys) {
    const base = baseItems.get(key)
    const pending = pendingItems.get(key)
    if (base && pending) {
      if (mappingSignature(base) !== mappingSignature(pending)) {
        diffs.push({ kind: 'modified', key, base, pending })
      }
    } else if (base) {
      diffs.push({ kind: 'removed', key, base })
    } else if (pending) {
      diffs.push({ kind: 'added', key, pending })
    }
  }

  const rank: Record<DiffKind, number> = { removed: 0, modified: 1, added: 2 }
  diffs.sort((left, right) => (
    rank[left.kind] - rank[right.kind]
    || left.key.localeCompare(right.key, 'en')
  ))

  return {
    diffs,
    added: diffs.filter((entry) => entry.kind === 'added').length,
    removed: diffs.filter((entry) => entry.kind === 'removed').length,
    modified: diffs.filter((entry) => entry.kind === 'modified').length,
  }
}

export function pickBaseVersion(versions: SkillVersion[], activeVersion: string) {
  const published = versions.filter(
    (version) => version.status === 'PUBLISHED' && version.version !== activeVersion,
  )

  published.sort((left, right) => {
    const leftTime = new Date(left.publishedAt).getTime()
    const rightTime = new Date(right.publishedAt).getTime()
    const leftValid = Number.isFinite(leftTime)
    const rightValid = Number.isFinite(rightTime)
    if (leftValid !== rightValid) {
      return leftValid ? -1 : 1
    }
    if (leftValid && rightValid && leftTime !== rightTime) {
      return rightTime - leftTime
    }
    if (left.id !== right.id) {
      return right.id - left.id
    }
    return right.version.localeCompare(left.version, 'en')
  })

  return published[0] ?? null
}

function mappingLabel(mapping?: ComplianceMapping) {
  if (!mapping) return '—'
  return [mapping.standard, mapping.controlId].filter(Boolean).join(' · ') || '—'
}

function MappingDetails({ mapping, emptyMessage }: { mapping?: ComplianceMapping; emptyMessage: string }) {
  const { t } = useTranslation()

  if (!mapping) {
    return (
      <div className="rounded-xl border border-dashed border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="min-w-0 overflow-hidden rounded-xl border border-border/70 bg-background/80 p-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="max-w-full break-all rounded-full bg-secondary px-2.5 py-0.5 font-mono text-xs text-secondary-foreground">
          {mapping.standard ?? t('compliance.unknownStandard')}
        </span>
        {mapping.version ? (
          <span className="max-w-full break-all font-mono text-xs text-muted-foreground">{mapping.version}</span>
        ) : null}
        <span className="max-w-full break-all font-mono text-sm font-semibold text-foreground">
          {mapping.controlId ?? '—'}
        </span>
      </div>
      {mapping.title ? <p className="mt-2 break-words text-sm leading-6">{mapping.title}</p> : null}

      {(mapping.evidence ?? []).length > 0 ? (
        <div className="mt-3 min-w-0 space-y-2">
          {(mapping.evidence ?? []).map((evidence, index) => (
            <div
              key={`${evidence.type ?? 'evidence'}-${evidence.path ?? evidence.url ?? index}`}
              className="min-w-0 rounded-lg border border-border/60 bg-muted/20 px-3 py-2 text-xs text-muted-foreground"
              data-compliance-evidence
            >
              <div className="min-w-0 break-all">
                {evidence.path ?? evidence.url ?? evidence.type ?? '—'}
              </div>
              {evidence.sha256 ? (
                <div className="mt-1 break-all font-mono leading-5">{evidence.sha256}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">{t('compliance.noEvidence')}</p>
      )}
    </div>
  )
}

function DiffItem({ entry }: { entry: DiffEntry }) {
  const { t } = useTranslation()
  const label = t(`review.complianceDiff${entry.kind[0].toUpperCase()}${entry.kind.slice(1)}`)
  const title = entry.pending?.title ?? entry.base?.title

  return (
    <details className="group min-w-0 overflow-hidden rounded-2xl border border-border/70 bg-card/90 p-4 shadow-sm">
      <summary className="flex min-w-0 cursor-pointer list-none items-start gap-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 [&::-webkit-details-marker]:hidden">
        <FileWarning className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" aria-hidden="true" />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className={cn(
              'rounded-full px-2.5 py-0.5 text-xs font-medium',
              entry.kind === 'added' && 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
              entry.kind === 'removed' && 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
              entry.kind === 'modified' && 'bg-amber-500/10 text-amber-800 dark:text-amber-200',
            )}>
              {label}
            </span>
            <span className="max-w-full break-all font-mono text-sm font-semibold">
              {mappingLabel(entry.base ?? entry.pending)}
            </span>
          </div>
          {title ? <p className="break-words text-sm text-muted-foreground">{title}</p> : null}
        </div>
        <span className="hidden shrink-0 items-center gap-1 text-xs text-muted-foreground sm:inline-flex">
          {t('review.complianceDiffViewDetails')}
          <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden="true" />
        </span>
      </summary>

      <div className="mt-4 grid min-w-0 gap-3 md:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('review.complianceDiffBaseVersion')}
          </div>
          <MappingDetails mapping={entry.base} emptyMessage={t('review.complianceDiffMissingFromBase')} />
        </div>
        <div className="min-w-0 space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('review.complianceDiffPendingVersion')}
          </div>
          <MappingDetails mapping={entry.pending} emptyMessage={t('review.complianceDiffMissingFromPending')} />
        </div>
      </div>
    </details>
  )
}

export function ReviewComplianceDiffPanel({
  baseVersion,
  pendingVersion,
  className,
}: ReviewComplianceDiffPanelProps) {
  const { t } = useTranslation()
  if (!baseVersion || !pendingVersion) return null

  const diff = compareComplianceSnapshots(
    baseVersion.complianceSnapshot,
    pendingVersion.complianceSnapshot,
  )
  if (diff.diffs.length === 0) return null

  return (
    <section className={cn(
      'min-w-0 overflow-hidden rounded-2xl border border-amber-500/25 bg-amber-500/5 p-4',
      className,
    )}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <FileWarning className="h-4 w-4 text-amber-600" aria-hidden="true" />
            {t('review.complianceDiffTitle')}
          </h3>
          <p className="break-words text-sm leading-6 text-muted-foreground">
            {t('review.complianceDiffDescription', {
              baseVersion: baseVersion.version,
              pendingVersion: pendingVersion.version,
            })}
          </p>
          <p className="break-words text-xs leading-5 text-muted-foreground">
            {t('review.complianceDiffClaimNotice')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(['added', 'removed', 'modified'] as const).map((kind) => (
            <span key={kind} className="rounded-full bg-background/80 px-2.5 py-1 text-xs font-medium">
              {t(`review.complianceDiff${kind[0].toUpperCase()}${kind.slice(1)}Label`, {
                count: diff[kind],
              })}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-4 grid min-w-0 gap-3 md:grid-cols-2">
        <div className="min-w-0 rounded-xl border border-border/60 bg-background/70 p-3">
          <div className="text-xs font-medium text-muted-foreground">{t('review.complianceDiffBaseDigest')}</div>
          <div className="mt-1 break-all font-mono text-xs leading-5">{baseVersion.complianceSnapshot?.digest ?? '—'}</div>
        </div>
        <div className="min-w-0 rounded-xl border border-border/60 bg-background/70 p-3">
          <div className="text-xs font-medium text-muted-foreground">{t('review.complianceDiffPendingDigest')}</div>
          <div className="mt-1 break-all font-mono text-xs leading-5">{pendingVersion.complianceSnapshot?.digest ?? '—'}</div>
        </div>
      </div>

      <div className="mt-4 grid min-w-0 gap-3">
        {diff.diffs.map((entry) => <DiffItem key={`${entry.kind}-${entry.key}`} entry={entry} />)}
      </div>
    </section>
  )
}

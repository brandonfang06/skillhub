import { useId, useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ComplianceSnapshot } from '@/api/types'
import { cn } from '@/shared/lib/utils'

interface ComplianceSnapshotPanelProps {
  snapshot?: ComplianceSnapshot | null
  className?: string
  defaultExpanded?: boolean
}

function declarationLabel(standard?: string | null, controlId?: string | null) {
  return [standard, controlId].filter(Boolean).join(' · ')
}

export function ComplianceSnapshotPanel({
  snapshot,
  className,
  defaultExpanded = false,
}: ComplianceSnapshotPanelProps) {
  const { t } = useTranslation()
  const detailId = useId()
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const items = snapshot?.items?.filter((item) => item.standard || item.controlId) ?? []

  if (items.length === 0) {
    return null
  }

  return (
    <section
      className={cn(
        'min-w-0 overflow-hidden rounded-2xl border border-amber-500/25 bg-amber-500/5 p-4',
        className,
      )}
      data-compliance-snapshot-panel
      aria-label={t('compliance.title')}
    >
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
            <FileText className="h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
            <span>{t('compliance.title')}</span>
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-800 dark:text-amber-200">
              {t('compliance.mappingCount', { count: items.length })}
            </span>
            {snapshot?.schemaVersion ? (
              <span className="rounded-full bg-secondary px-2 py-0.5 font-mono text-xs text-secondary-foreground">
                {t('compliance.schemaVersion', { version: snapshot.schemaVersion })}
              </span>
            ) : null}
          </div>
          <p className="break-words text-xs leading-5 text-muted-foreground">
            {t('compliance.publisherClaimNotice')} {t('compliance.notCertification')}
          </p>
        </div>

        <button
          type="button"
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border/70 bg-background/80 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
          aria-expanded={isExpanded}
          aria-controls={detailId}
          onClick={() => setIsExpanded((value) => !value)}
        >
          {isExpanded ? (
            <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {isExpanded ? t('common.collapse') : t('common.expand')}
        </button>
      </div>

      <div className="mt-3 flex min-w-0 flex-wrap gap-2">
        {items.slice(0, isExpanded ? items.length : 2).map((item, index) => (
          <span
            key={`${item.standard ?? 'standard'}-${item.version ?? 'version'}-${item.controlId ?? index}`}
            className="inline-flex max-w-full min-w-0 items-center rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-900 dark:text-amber-100"
          >
            <span className="truncate">{declarationLabel(item.standard, item.controlId)}</span>
          </span>
        ))}
        {!isExpanded && items.length > 2 ? (
          <span className="inline-flex items-center rounded-full border border-dashed border-border/70 px-2.5 py-1 text-xs text-muted-foreground">
            +{items.length - 2}
          </span>
        ) : null}
      </div>

      <div
        id={detailId}
        className={isExpanded ? 'mt-4 min-w-0 space-y-3' : undefined}
        data-compliance-snapshot-detail
      >
        {isExpanded ? (
          <>
          {snapshot?.digest ? (
            <div className="min-w-0 rounded-xl border border-border/60 bg-background/70 p-3">
              <div className="text-xs font-medium text-muted-foreground">{t('compliance.digest')}</div>
              <div className="mt-1 break-all font-mono text-xs leading-5 text-foreground">
                {snapshot.digest}
              </div>
            </div>
          ) : null}

          {items.map((item, index) => (
            <article
              key={`${item.standard ?? 'standard'}-${item.version ?? 'version'}-${item.controlId ?? index}`}
              className="min-w-0 rounded-xl border border-border/60 bg-background/70 p-3"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="max-w-full break-all rounded-full bg-secondary px-2 py-0.5 font-mono text-xs text-secondary-foreground">
                  {item.standard ?? t('compliance.unknownStandard')}
                </span>
                {item.version ? (
                  <span className="max-w-full break-all font-mono text-xs text-muted-foreground">
                    {item.version}
                  </span>
                ) : null}
                <span className="max-w-full break-all font-mono text-sm font-semibold text-foreground">
                  {item.controlId ?? '—'}
                </span>
              </div>
              {item.title ? (
                <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">{item.title}</p>
              ) : null}

              {(item.evidence ?? []).length > 0 ? (
                <div className="mt-3 min-w-0 space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">{t('compliance.evidence')}</div>
                  {(item.evidence ?? []).map((evidence, evidenceIndex) => (
                    <div
                      key={`${evidence.type ?? 'evidence'}-${evidence.path ?? evidence.url ?? evidenceIndex}`}
                      className="min-w-0 rounded-lg border border-border/60 bg-muted/20 px-3 py-2 text-xs text-muted-foreground"
                      data-compliance-evidence
                    >
                      <div className="flex min-w-0 flex-wrap items-start gap-2">
                        <span className="shrink-0 rounded-full bg-background px-2 py-0.5 font-medium text-foreground">
                          {evidence.type ?? t('compliance.evidence')}
                        </span>
                        {evidence.url ? (
                          <a
                            className="min-w-0 break-all text-primary underline-offset-4 hover:underline"
                            href={evidence.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <ExternalLink className="mr-1 inline h-3 w-3" aria-hidden="true" />
                            {evidence.url}
                          </a>
                        ) : evidence.path ? (
                          <span className="min-w-0 break-all font-mono">{evidence.path}</span>
                        ) : null}
                      </div>
                      {evidence.sha256 ? (
                        <div className="mt-2 break-all font-mono leading-5">{evidence.sha256}</div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
          </>
        ) : null}
      </div>
    </section>
  )
}

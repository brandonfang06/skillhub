import { ExternalLink, GitBranch } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SourceProvenance } from '@/api/types'
import { Card } from '@/shared/ui/card'

interface SourceProvenanceCardProps {
  provenance?: SourceProvenance | null
}

export function SourceProvenanceCard({ provenance }: SourceProvenanceCardProps) {
  const { t } = useTranslation()
  if (!provenance) return null

  const revisionLabel = provenance.sourceRef
    ? `${provenance.sourceRefType.toLowerCase()}: ${provenance.sourceRef}`
    : provenance.repositoryRevisionSha.slice(0, 12)

  return (
    <Card data-testid="source-provenance" className="space-y-3 border-sky-500/25 bg-sky-500/5 p-4">
      <div className="flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-sky-600" />
        <h3 className="text-sm font-semibold font-heading text-foreground">
          {t('skillDetail.sourceProvenanceTitle')}
        </h3>
      </div>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">{t('skillDetail.sourceRevision')}</dt>
          <dd className="mt-1 break-all font-mono text-foreground">{revisionLabel}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">{t('skillDetail.sourcePath')}</dt>
          <dd className="mt-1 break-all font-mono text-foreground">{provenance.sourcePath}</dd>
        </div>
      </dl>
      <a
        className="inline-flex items-center gap-1.5 text-sm font-medium text-sky-700 hover:underline"
        href={provenance.browseUrl}
        target="_blank"
        rel="noreferrer"
      >
        {t('skillDetail.openSourceRepository')}
        <ExternalLink className="h-3.5 w-3.5" />
      </a>
    </Card>
  )
}

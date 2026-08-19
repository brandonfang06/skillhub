import { Clock, UserRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { VersionAttribution } from '@/api/types'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { Card } from '@/shared/ui/card'

interface VersionAttributionCardProps {
  attribution?: VersionAttribution | null
}

export function VersionAttributionCard({ attribution }: VersionAttributionCardProps) {
  const { t, i18n } = useTranslation()
  if (!attribution || attribution.type !== 'NATIVE_SUBMISSION') return null

  return (
    <Card data-testid="version-attribution" className="space-y-3 p-4">
      <div className="flex items-center gap-2">
        <UserRound className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold font-heading text-foreground">
          {t('skillDetail.versionAttributionTitle')}
        </h3>
      </div>
      <dl className="grid min-w-0 gap-3 text-sm sm:grid-cols-2">
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">{t('skillDetail.submittedBy')}</dt>
          <dd className="mt-1 break-words font-medium text-foreground">
            {attribution.submittedByName || attribution.submittedBy}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {t('skillDetail.submittedAt')}
          </dt>
          <dd className="mt-1 text-foreground">
            {formatLocalDateTime(attribution.submittedAt, i18n.language)}
          </dd>
        </div>
      </dl>
    </Card>
  )
}

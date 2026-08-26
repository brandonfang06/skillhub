import type { SkillSummary } from '@/api/types'
import { useAuth } from '@/features/auth/use-auth'
import { useStar } from '@/features/social/use-star'
import { Card } from '@/shared/ui/card'
import { NamespaceBadge } from '@/shared/components/namespace-badge'
import { getHeadlineVersion } from '@/shared/lib/skill-lifecycle'
import { formatCompactCount } from '@/shared/lib/number-format'
import { Bookmark, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/shared/lib/utils'

interface SkillCardProps {
  skill: SkillSummary
  onClick?: () => void
  highlightStarred?: boolean
  selectionMode?: boolean
  selected?: boolean
  selectionDisabled?: boolean
  onSelectionChange?: (selected: boolean) => void
}

/**
 * Reusable card for displaying one skill in lists such as landing, namespace, search, and stars.
 */
export function SkillCard({
  skill,
  onClick,
  highlightStarred = true,
  selectionMode = false,
  selected = false,
  selectionDisabled = false,
  onSelectionChange,
}: SkillCardProps) {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuth()
  const { data: starStatus } = useStar(skill.id, highlightStarred && isAuthenticated)
  const showStarredHighlight = highlightStarred && isAuthenticated && starStatus?.starred
  const headlineVersion = getHeadlineVersion(skill)
  const isInteractive = typeof onClick === 'function'
  const complianceItems = skill.complianceSnapshot?.items?.filter(
    (item) => item.standard || item.controlId,
  ) ?? []

  return (
    <Card
      className={cn(
        'h-full p-5 cursor-pointer group relative overflow-hidden bg-white border shadow-sm transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2',
        selected && 'ring-2 ring-primary/70',
      )}
      style={{ borderColor: 'hsl(var(--border-card))' }}
      onClick={onClick}
      onKeyDown={(event) => {
        if (!isInteractive) {
          return
        }

        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onClick()
        }
      }}
      role={isInteractive ? 'link' : undefined}
      tabIndex={isInteractive ? 0 : undefined}
    >
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between mb-3">
          <div className="flex min-w-0 items-start gap-3">
            {selectionMode && (
              <input
                type="checkbox"
                aria-label={t('installSelection.selectSkill', { skill: skill.displayName })}
                checked={selected}
                disabled={selectionDisabled}
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
                onChange={(event) => onSelectionChange?.(event.target.checked)}
                className="mt-1 h-5 w-5 shrink-0 cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50"
              />
            )}
            <h3 className="font-semibold text-lg group-hover:text-primary transition-colors" style={{ color: 'hsl(var(--foreground))' }}>
              {skill.displayName}
            </h3>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <NamespaceBadge type="TEAM" name={`@${skill.namespace}`} />
          </div>
        </div>

        {skill.summary && (
          <p className="text-sm text-muted-foreground mb-4 line-clamp-2 leading-relaxed">
            {skill.summary}
          </p>
        )}

        {complianceItems.length > 0 ? (
          <div className="mb-4 flex min-w-0 flex-wrap gap-1.5">
            {complianceItems.slice(0, 2).map((item, index) => (
              <span
                key={`${item.standard ?? 'standard'}-${item.version ?? 'version'}-${item.controlId ?? index}`}
                className="inline-flex max-w-full min-w-0 items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-900 dark:text-amber-100"
                title={item.title ?? undefined}
                aria-label={t('compliance.badgeLabel', {
                  standard: item.standard ?? t('compliance.unknownStandard'),
                  controlId: item.controlId ?? '—',
                })}
                data-compliance-claim-badge
              >
                <FileText className="h-3 w-3 shrink-0" aria-hidden="true" />
                <span className="truncate">
                  {[item.standard, item.controlId].filter(Boolean).join(' · ')}
                </span>
              </span>
            ))}
            {complianceItems.length > 2 ? (
              <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
                +{complianceItems.length - 2}
              </span>
            ) : null}
          </div>
        ) : null}

        <div className="mt-auto flex items-center gap-4 text-xs text-muted-foreground">
          {headlineVersion && (
            <span className="px-2.5 py-1 rounded-full bg-secondary/60 font-mono">
              v{headlineVersion.version}
            </span>
          )}
          <span className="flex items-center gap-1">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" />
            </svg>
            {formatCompactCount(skill.downloadCount)}
          </span>
          <span
            className={`flex items-center gap-1 ${showStarredHighlight ? 'font-semibold text-primary' : ''}`}
          >
            <Bookmark className={`w-3.5 h-3.5 ${showStarredHighlight ? 'fill-current' : ''}`} />
            {skill.starCount}
          </span>
          {skill.ratingAvg !== undefined && skill.ratingCount > 0 && (
            <span className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5 text-primary" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
              </svg>
              {skill.ratingAvg.toFixed(1)}
            </span>
          )}
        </div>
      </div>
    </Card>
  )
}

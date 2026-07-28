import { useTranslation } from 'react-i18next'

import { NamespaceBadge } from '@/shared/components/namespace-badge'
import { Card } from '@/shared/ui/card'

import type { CollectionSummary } from './api'

export function CollectionCard({
  collection,
  onClick,
}: {
  collection: CollectionSummary
  onClick?: () => void
}) {
  const { t } = useTranslation()
  const isInteractive = typeof onClick === 'function'
  const published = collection.latestPublishedVersion

  return (
    <Card
      className="group relative h-full cursor-pointer overflow-hidden border bg-white p-5 shadow-sm transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2"
      onClick={onClick}
      onKeyDown={(event) => {
        if (
          isInteractive &&
          (event.key === 'Enter' || event.key === ' ')
        ) {
          event.preventDefault()
          onClick()
        }
      }}
      role={isInteractive ? 'link' : undefined}
      tabIndex={isInteractive ? 0 : undefined}
    >
      <div className="flex h-full flex-col">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold transition-colors group-hover:text-primary">
              {collection.displayName}
            </h3>
            <p className="font-mono text-xs text-muted-foreground">
              @{collection.namespace}/{collection.slug}
            </p>
          </div>
          <NamespaceBadge type="TEAM" name={`@${collection.namespace}`} />
        </div>

        {collection.summary ? (
          <p className="mb-4 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
            {collection.summary}
          </p>
        ) : null}

        <div className="mt-auto flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {published ? (
            <>
              <span className="rounded-full bg-secondary/60 px-2.5 py-1 font-mono">
                v{published.version}
              </span>
              <span>
                {published.memberCount} {t('collectionCard.members')}
              </span>
            </>
          ) : (
            <span>{t('collectionCard.unpublished')}</span>
          )}
          {collection.status === 'ARCHIVED' ? (
            <span className="rounded-full border px-2.5 py-1">
              {t('collectionCard.archived')}
            </span>
          ) : null}
          {collection.canCurate && collection.draft ? (
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-primary">
              {t('collectionCard.draft')}
            </span>
          ) : null}
        </div>
      </div>
    </Card>
  )
}

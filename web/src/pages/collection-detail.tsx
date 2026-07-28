import { useParams } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { getCollectionsRuntimeConfig } from '@/api/client'
import { CollectionInstallCommand } from '@/features/collection/collection-install-command'
import { useCollection } from '@/features/collection/use-collections'
import { EmptyState } from '@/shared/components/empty-state'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'

export function CollectionDetailPage() {
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

  if (!runtime.enabled) {
    return <EmptyState title={t('collectionDetail.notFound')} />
  }
  if (isLoading) {
    return <div className="h-48 animate-shimmer rounded-xl" />
  }
  if (!data || (!data.latestPublishedVersion && !data.canCurate)) {
    return <EmptyState title={t('collectionDetail.notFound')} />
  }

  const published = data.latestPublishedVersion
  const publishedIsDegraded =
    published?.members.some(
      (member) =>
        member.skillId === null || member.skillVersionId === null,
    ) ?? false

  return (
    <div className="space-y-8 animate-fade-up">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-heading text-3xl font-bold">
            {data.displayName}
          </h1>
          {data.status === 'ARCHIVED' ? (
            <span className="rounded-full border px-3 py-1 text-xs">
              {t('collectionCard.archived')}
            </span>
          ) : null}
        </div>
        <p className="font-mono text-sm text-muted-foreground">
          @{data.namespace}/{data.slug}
        </p>
        <p className="max-w-3xl text-muted-foreground">{data.summary}</p>
        {data.canCurate ? (
          <a
            className="inline-flex text-sm font-medium text-primary hover:underline"
            href={`/dashboard/namespaces/${encodeURIComponent(data.namespace)}/collections/${encodeURIComponent(data.slug)}`}
          >
            {t('collectionDetail.maintain')}
          </a>
        ) : null}
      </header>

      {published ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>
                {t('collectionDetail.members', {
                  version: published.version,
                  count: published.memberCount,
                })}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-3">
                {[...published.members]
                  .sort((a, b) => a.position - b.position)
                  .map((member) => (
                    <li
                      key={
                        member.skillVersionId ??
                        `${member.namespace}/${member.skillSlug}@${member.version}:${member.position}`
                      }
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"
                    >
                      {member.skillId === null ? (
                        <span className="font-mono text-sm text-muted-foreground">
                          {member.skillSlug}@{member.version}
                        </span>
                      ) : (
                        <a
                          className="font-mono text-sm text-primary hover:underline"
                          href={`/space/${encodeURIComponent(member.namespace)}/${encodeURIComponent(member.skillSlug)}`}
                        >
                          {member.skillSlug}@{member.version}
                        </a>
                      )}
                      {member.note ? (
                        <span className="text-sm text-muted-foreground">
                          {member.note}
                        </span>
                      ) : null}
                    </li>
                  ))}
              </ol>
            </CardContent>
          </Card>

          {publishedIsDegraded ? (
            <p className="text-sm text-muted-foreground" role="status">
              {t('collectionDetail.degraded')}
            </p>
          ) : (
            <CollectionInstallCommand
              input={{
                npmRegistry: runtime.cli?.npmRegistry ?? '',
                packageName: runtime.cli?.packageName ?? '',
                cliVersion: runtime.cli?.version ?? '',
                skillhubBaseUrl: runtime.skillhubBaseUrl ?? '',
                namespace: data.namespace,
                collection: data.slug,
                collectionVersion: published.version,
              }}
            />
          )}
        </>
      ) : (
        <EmptyState title={t('collectionDetail.unpublished')} />
      )}
    </div>
  )
}

import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { getCollectionsRuntimeConfig } from '@/api/client'
import type { NamespaceRole } from '@/api/types'
import { useAuth } from '@/features/auth/use-auth'
import { CollectionCard } from '@/features/collection/collection-card'
import {
  useCollections,
  useCreateCollection,
} from '@/features/collection/use-collections'
import { useMyNamespaces } from '@/features/namespace/use-my-namespaces'
import { DashboardPageHeader } from '@/shared/components/dashboard-page-header'
import { EmptyState } from '@/shared/components/empty-state'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import { Textarea } from '@/shared/ui/textarea'

export function canCreateCollection(
  namespaceRole: NamespaceRole | undefined,
  platformRoles: string[],
): boolean {
  return (
    namespaceRole === 'OWNER' ||
    namespaceRole === 'ADMIN' ||
    platformRoles.includes('SKILL_ADMIN') ||
    platformRoles.includes('SUPER_ADMIN')
  )
}

export function isValidCollectionSlug(value: string): boolean {
  return /^[a-z0-9][a-z0-9._-]*$/.test(value)
}

export function NamespaceCollectionsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const params = useParams({ strict: false }) as { namespace?: string }
  const namespace = params.namespace ?? ''
  const runtime = getCollectionsRuntimeConfig()
  const { user } = useAuth()
  const { data: managedNamespaces = [] } = useMyNamespaces()
  const { data, isLoading } = useCollections(namespace, runtime.enabled)
  const createCollection = useCreateCollection(namespace)
  const [slug, setSlug] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [summary, setSummary] = useState('')

  const namespaceRole = managedNamespaces.find(
    (candidate) => candidate.slug === namespace,
  )?.currentUserRole
  const canCreate = canCreateCollection(
    namespaceRole,
    user?.platformRoles ?? [],
  )

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    if (
      !canCreate ||
      !isValidCollectionSlug(slug) ||
      !displayName.trim() ||
      !summary.trim()
    ) {
      return
    }
    try {
      const created = await createCollection.mutateAsync({
        slug,
        displayName: displayName.trim(),
        summary: summary.trim(),
      })
      toast.success(t('collectionAdmin.createSuccess'))
      navigate({
        to: `/dashboard/namespaces/${encodeURIComponent(namespace)}/collections/${encodeURIComponent(created.slug)}`,
      })
    } catch (error) {
      toast.error(
        t('collectionAdmin.createError'),
        error instanceof Error ? error.message : '',
      )
    }
  }

  if (!runtime.enabled) {
    return <EmptyState title={t('collectionAdmin.disabled')} />
  }

  return (
    <div className="space-y-8 animate-fade-up">
      <DashboardPageHeader
        title={t('collectionAdmin.title')}
        subtitle={`@${namespace}`}
      />

      {canCreate ? (
        <Card className="p-6">
          <form className="space-y-4" onSubmit={handleCreate}>
            <h2 className="font-heading text-xl font-semibold">
              {t('collectionAdmin.createTitle')}
            </h2>
            <div className="grid gap-4 md:grid-cols-2">
              <Input
                value={slug}
                onChange={(event) => setSlug(event.target.value.toLowerCase())}
                placeholder={t('collectionAdmin.slug')}
                aria-label={t('collectionAdmin.slug')}
              />
              <Input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder={t('collectionAdmin.displayName')}
                aria-label={t('collectionAdmin.displayName')}
              />
            </div>
            <Textarea
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              placeholder={t('collectionAdmin.summary')}
              aria-label={t('collectionAdmin.summary')}
            />
            <Button
              type="submit"
              disabled={
                createCollection.isPending ||
                !isValidCollectionSlug(slug) ||
                !displayName.trim() ||
                !summary.trim()
              }
            >
              {t('collectionAdmin.create')}
            </Button>
          </form>
        </Card>
      ) : (
        <Card className="p-4 text-sm text-muted-foreground">
          {t('collectionAdmin.namespaceOwnerOnly')}
        </Card>
      )}

      {isLoading ? (
        <div className="h-48 animate-shimmer rounded-xl" />
      ) : data && data.items.length > 0 ? (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
          {data.items.map((collection) => (
            <CollectionCard
              key={collection.collectionId}
              collection={collection}
              onClick={() =>
                navigate({
                  to: `/dashboard/namespaces/${encodeURIComponent(namespace)}/collections/${encodeURIComponent(collection.slug)}`,
                })
              }
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={t('collectionAdmin.emptyTitle')}
          description={t('collectionAdmin.emptyDescription')}
        />
      )}
    </div>
  )
}

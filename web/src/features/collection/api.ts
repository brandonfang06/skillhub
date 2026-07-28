import { fetchJson, getCsrfHeaders, WEB_API_PREFIX } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type CollectionCreateInput =
  components['schemas']['CollectionCreateRequest']
export type CollectionDetail =
  components['schemas']['CollectionDetailResponse']
export type CollectionDraftInput =
  components['schemas']['CollectionDraftReplaceRequest']
export type CollectionList =
  components['schemas']['CollectionListResponse']
export type CollectionMember =
  components['schemas']['CollectionMemberResponse']
export type CollectionMemberInput =
  components['schemas']['CollectionMemberInput']
export type CollectionPublishInput =
  components['schemas']['CollectionPublishRequest']
export type CollectionSummary =
  components['schemas']['CollectionSummaryResponse']
export type CollectionVersion =
  components['schemas']['CollectionVersionResponse']
export type CollectionStatus = 'ACTIVE' | 'ARCHIVED'

function segment(value: string): string {
  return encodeURIComponent(value)
}

function collectionPath(namespace: string, collection: string): string {
  return `${WEB_API_PREFIX}/collections/${segment(namespace)}/${segment(collection)}`
}

function mutationHeaders(extra?: Record<string, string>): HeadersInit {
  return getCsrfHeaders({
    'Content-Type': 'application/json',
    ...extra,
  })
}

export const collectionApi = {
  async list(namespace: string): Promise<CollectionList> {
    return fetchJson<CollectionList>(
      `${WEB_API_PREFIX}/namespaces/${segment(namespace)}/collections`,
    )
  },

  async detail(namespace: string, collection: string): Promise<CollectionDetail> {
    return fetchJson<CollectionDetail>(collectionPath(namespace, collection))
  },

  async create(
    namespace: string,
    input: CollectionCreateInput,
    idempotencyKey: string,
  ): Promise<CollectionDetail> {
    return fetchJson<CollectionDetail>(
      `${WEB_API_PREFIX}/namespaces/${segment(namespace)}/collections`,
      {
        method: 'POST',
        headers: mutationHeaders({ 'Idempotency-Key': idempotencyKey }),
        body: JSON.stringify(input),
      },
    )
  },

  async createDraft(
    namespace: string,
    collection: string,
  ): Promise<CollectionVersion> {
    return fetchJson<CollectionVersion>(
      `${collectionPath(namespace, collection)}/draft`,
      {
        method: 'POST',
        headers: getCsrfHeaders(),
      },
    )
  },

  async replaceDraft(
    namespace: string,
    collection: string,
    input: CollectionDraftInput,
    draftRevision: number,
  ): Promise<CollectionVersion> {
    return fetchJson<CollectionVersion>(
      `${collectionPath(namespace, collection)}/draft`,
      {
        method: 'PUT',
        headers: mutationHeaders({ 'If-Match': `"${draftRevision}"` }),
        body: JSON.stringify(input),
      },
    )
  },

  async deleteDraft(
    namespace: string,
    collection: string,
  ): Promise<{ deleted: boolean }> {
    return fetchJson<{ deleted: boolean }>(
      `${collectionPath(namespace, collection)}/draft`,
      {
        method: 'DELETE',
        headers: getCsrfHeaders(),
      },
    )
  },

  async publish(
    namespace: string,
    collection: string,
    input: CollectionPublishInput,
    idempotencyKey: string,
  ): Promise<CollectionVersion> {
    return fetchJson<CollectionVersion>(
      `${collectionPath(namespace, collection)}/publish`,
      {
        method: 'POST',
        headers: mutationHeaders({ 'Idempotency-Key': idempotencyKey }),
        body: JSON.stringify(input),
      },
    )
  },

  async setStatus(
    namespace: string,
    collection: string,
    status: CollectionStatus,
    reason?: string,
  ): Promise<CollectionDetail> {
    return fetchJson<CollectionDetail>(
      `${collectionPath(namespace, collection)}/status`,
      {
        method: 'PUT',
        headers: mutationHeaders(),
        body: JSON.stringify({
          status,
          ...(reason?.trim() ? { reason: reason.trim() } : {}),
        }),
      },
    )
  },
}

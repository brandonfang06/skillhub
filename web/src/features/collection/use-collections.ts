import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'

import {
  getCollectionDetailQueryKey,
  getCollectionListQueryKey,
} from '@/shared/hooks/query-keys'

import {
  collectionApi,
  type CollectionCreateInput,
  type CollectionDraftInput,
  type CollectionPublishInput,
  type CollectionStatus,
} from './api'

function createIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function collectionListQueryOptions(
  namespace: string,
  enabled = true,
) {
  return {
    queryKey: getCollectionListQueryKey(namespace),
    queryFn: () => collectionApi.list(namespace),
    enabled: enabled && Boolean(namespace),
  }
}

export function collectionDetailQueryOptions(
  namespace: string,
  collection: string,
  enabled = true,
) {
  return {
    queryKey: getCollectionDetailQueryKey(namespace, collection),
    queryFn: () => collectionApi.detail(namespace, collection),
    enabled: enabled && Boolean(namespace) && Boolean(collection),
  }
}

export async function invalidateCollectionQueries(
  queryClient: Pick<QueryClient, 'invalidateQueries'>,
  namespace: string,
  collection?: string,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: getCollectionListQueryKey(namespace),
  })
  if (collection) {
    await queryClient.invalidateQueries({
      queryKey: getCollectionDetailQueryKey(namespace, collection),
    })
  }
}

export function useCollections(namespace: string, enabled = true) {
  return useQuery(collectionListQueryOptions(namespace, enabled))
}

export function useCollection(
  namespace: string,
  collection: string,
  enabled = true,
) {
  return useQuery(
    collectionDetailQueryOptions(namespace, collection, enabled),
  )
}

export function useCreateCollection(namespace: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CollectionCreateInput) =>
      collectionApi.create(namespace, input, createIdempotencyKey()),
    onSuccess: (collection) =>
      invalidateCollectionQueries(queryClient, namespace, collection.slug),
  })
}

export function useCreateCollectionDraft(
  namespace: string,
  collection: string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => collectionApi.createDraft(namespace, collection),
    onSuccess: () =>
      invalidateCollectionQueries(queryClient, namespace, collection),
  })
}

export function useSaveCollectionDraft(
  namespace: string,
  collection: string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      input,
      draftRevision,
    }: {
      input: CollectionDraftInput
      draftRevision: number
    }) =>
      collectionApi.replaceDraft(
        namespace,
        collection,
        input,
        draftRevision,
      ),
    onSuccess: () =>
      invalidateCollectionQueries(queryClient, namespace, collection),
  })
}

export function useDeleteCollectionDraft(
  namespace: string,
  collection: string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => collectionApi.deleteDraft(namespace, collection),
    onSuccess: () =>
      invalidateCollectionQueries(queryClient, namespace, collection),
  })
}

export function usePublishCollection(
  namespace: string,
  collection: string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CollectionPublishInput) =>
      collectionApi.publish(
        namespace,
        collection,
        input,
        createIdempotencyKey(),
      ),
    onSuccess: () =>
      invalidateCollectionQueries(queryClient, namespace, collection),
  })
}

export function useSetCollectionStatus(
  namespace: string,
  collection: string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      status,
      reason,
    }: {
      status: CollectionStatus
      reason?: string
    }) => collectionApi.setStatus(namespace, collection, status, reason),
    onSuccess: () =>
      invalidateCollectionQueries(queryClient, namespace, collection),
  })
}

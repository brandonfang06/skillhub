import { useMutation, useQueryClient } from '@tanstack/react-query'

import {
  repositoryImportApi,
  type RepositoryImportCollectionDraftRequest,
  type RepositoryImportIngestRequest,
  type RepositoryImportPreviewRequest,
} from './api'

export function usePreviewRepositoryImport(namespace: string) {
  return useMutation({
    mutationFn: (request: RepositoryImportPreviewRequest) =>
      repositoryImportApi.preview(namespace, request),
  })
}

export function useIngestRepositoryImport() {
  return useMutation({
    mutationFn: ({
      importId,
      request,
    }: {
      importId: number
      request: RepositoryImportIngestRequest
    }) => repositoryImportApi.ingest(importId, request),
  })
}

export function useCheckRepositoryImportUpdates() {
  return useMutation({
    mutationFn: (importId: number) =>
      repositoryImportApi.checkUpdates(importId),
  })
}

export function useSeedRepositoryImportCollection(
  namespace: string,
  collection: string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      importId,
      request,
    }: {
      importId: number
      request: RepositoryImportCollectionDraftRequest
    }) => repositoryImportApi.seedCollectionDraft(importId, request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['collections', 'detail', namespace, collection],
      })
      await queryClient.invalidateQueries({
        queryKey: ['collections', 'namespace', namespace],
      })
    },
  })
}

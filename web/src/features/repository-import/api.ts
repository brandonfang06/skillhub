import { fetchJson, getCsrfHeaders, WEB_API_PREFIX } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type RepositoryImportPreviewRequest =
  components['schemas']['RepositoryImportPreviewRequest']
export type RepositoryImportCandidate =
  components['schemas']['RepositoryImportCandidateResponse']
export type RepositoryImportPreview =
  components['schemas']['RepositoryImportResponse']
export type RepositoryImportSelection =
  components['schemas']['RepositoryImportSelection']
export type RepositoryImportIngestRequest =
  components['schemas']['RepositoryImportIngestRequest']
export type RepositoryImportCandidateResult =
  components['schemas']['RepositoryImportCandidateResult']
export type RepositoryImportIngestResponse =
  components['schemas']['RepositoryImportIngestResponse']
export type RepositoryImportCollectionDraftRequest =
  components['schemas']['RepositoryImportCollectionDraftRequest']
export type RepositoryImportCollectionDraftResponse =
  components['schemas']['RepositoryImportCollectionDraftResponse']
export type RepositoryImportUpdateCheckResponse =
  components['schemas']['RepositoryImportUpdateCheckResponse']

function mutationInit(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: getCsrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  }
}

export const repositoryImportApi = {
  preview(
    namespace: string,
    request: RepositoryImportPreviewRequest,
  ): Promise<RepositoryImportPreview> {
    return fetchJson<RepositoryImportPreview>(
      `${WEB_API_PREFIX}/namespaces/${encodeURIComponent(namespace)}/repository-imports/preview`,
      mutationInit(request),
    )
  },

  ingest(
    importId: number,
    request: RepositoryImportIngestRequest,
  ): Promise<RepositoryImportIngestResponse> {
    return fetchJson<RepositoryImportIngestResponse>(
      `${WEB_API_PREFIX}/repository-imports/${importId}/ingest`,
      mutationInit(request),
    )
  },

  checkUpdates(importId: number): Promise<RepositoryImportUpdateCheckResponse> {
    return fetchJson<RepositoryImportUpdateCheckResponse>(
      `${WEB_API_PREFIX}/repository-imports/${importId}/check-updates`,
      {
        method: 'POST',
        headers: getCsrfHeaders(),
      },
    )
  },

  seedCollectionDraft(
    importId: number,
    request: RepositoryImportCollectionDraftRequest,
  ): Promise<RepositoryImportCollectionDraftResponse> {
    return fetchJson<RepositoryImportCollectionDraftResponse>(
      `${WEB_API_PREFIX}/repository-imports/${importId}/collection-draft`,
      mutationInit(request),
    )
  },
}

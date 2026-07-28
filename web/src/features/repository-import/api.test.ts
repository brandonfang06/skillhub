import { beforeEach, describe, expect, it, vi } from 'vitest'

const { fetchJson, getCsrfHeaders } = vi.hoisted(() => ({
  fetchJson: vi.fn(),
  getCsrfHeaders: vi.fn((headers?: HeadersInit) => headers ?? {}),
}))
vi.mock('@/api/client', () => ({
  fetchJson,
  getCsrfHeaders,
  WEB_API_PREFIX: '/api/web',
}))

import { repositoryImportApi } from './api'

beforeEach(() => {
  fetchJson.mockReset()
  getCsrfHeaders.mockClear()
})

describe('repositoryImportApi', () => {
  it('previews an allowlisted project path and ref', async () => {
    fetchJson.mockResolvedValue({ importId: 9 })

    await repositoryImportApi.preview('opensource', {
      projectPath: 'oss-mirrors/project',
      ref: 'main',
    })

    expect(fetchJson).toHaveBeenCalledWith(
      '/api/web/namespaces/opensource/repository-imports/preview',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          projectPath: 'oss-mirrors/project',
          ref: 'main',
        }),
      }),
    )
  })

  it('ingests explicit candidates and seeds a collection draft', async () => {
    fetchJson.mockResolvedValue({})
    await repositoryImportApi.ingest(9, {
      candidates: [
        {
          candidateId: 1,
          targetSlug: 'alpha',
          targetVersion: '1.0.0',
          visibility: 'NAMESPACE_ONLY',
        },
      ],
    })
    await repositoryImportApi.seedCollectionDraft(9, {
      collectionSlug: 'superpowers',
      displayName: 'Superpowers',
      summary: 'Curated',
      candidateIds: [1],
    })

    expect(fetchJson).toHaveBeenNthCalledWith(
      1,
      '/api/web/repository-imports/9/ingest',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchJson).toHaveBeenNthCalledWith(
      2,
      '/api/web/repository-imports/9/collection-draft',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('checks the stored project and ref for an immutable update preview', async () => {
    fetchJson.mockResolvedValue({ changed: false })

    await repositoryImportApi.checkUpdates(9)

    expect(fetchJson).toHaveBeenCalledWith(
      '/api/web/repository-imports/9/check-updates',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})

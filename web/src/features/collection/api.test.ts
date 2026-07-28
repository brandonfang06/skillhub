import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { collectionApi } from './api'

const fetchMock = vi.fn()

function envelope(data: unknown) {
  return new Response(JSON.stringify({
    code: 0,
    msg: 'ok',
    data,
    timestamp: '2026-07-27T00:00:00Z',
    requestId: 'request-1',
  }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function lastRequest(): [string, RequestInit] {
  const call = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]
  return [String(call?.[0]), (call?.[1] ?? {}) as RequestInit]
}

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockImplementation(() => Promise.resolve(envelope({})))
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('document', { cookie: 'XSRF-TOKEN=csrf-token' })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('collectionApi read requests', () => {
  it('lists and reads encoded collection coordinates', async () => {
    await collectionApi.list('team space')
    expect(lastRequest()[0]).toBe('/api/web/namespaces/team%20space/collections')
    expect(lastRequest()[1].method).toBeUndefined()

    await collectionApi.detail('team space', 'starter kit')
    expect(lastRequest()[0]).toBe('/api/web/collections/team%20space/starter%20kit')
  })
})

describe('collectionApi mutation requests', () => {
  it('creates with JSON, CSRF, and idempotency headers', async () => {
    await collectionApi.create('opensource', {
      slug: 'superpowers',
      displayName: 'Superpowers',
      summary: 'Core workflow skills',
    }, 'create-key')

    const [url, init] = lastRequest()
    const headers = new Headers(init.headers)
    expect(url).toBe('/api/web/namespaces/opensource/collections')
    expect(init.method).toBe('POST')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('X-XSRF-TOKEN')).toBe('csrf-token')
    expect(headers.get('Idempotency-Key')).toBe('create-key')
  })

  it('creates, replaces, and deletes a draft with exact concurrency headers', async () => {
    await collectionApi.createDraft('opensource', 'superpowers')
    expect(lastRequest()[1].method).toBe('POST')

    await collectionApi.replaceDraft('opensource', 'superpowers', {
      displayName: 'Superpowers',
      summary: 'Core workflow skills',
      releaseNotes: 'Refresh',
      members: [{
        skillId: 80,
        skillVersionId: 901,
        position: 0,
      }],
    }, 7)
    const replaceHeaders = new Headers(lastRequest()[1].headers)
    expect(lastRequest()[1].method).toBe('PUT')
    expect(replaceHeaders.get('If-Match')).toBe('"7"')

    await collectionApi.deleteDraft('opensource', 'superpowers')
    expect(lastRequest()[1].method).toBe('DELETE')
  })

  it('publishes an explicit version with an idempotency key', async () => {
    await collectionApi.publish('opensource', 'superpowers', {
      version: '1.2.0',
      draftRevision: 7,
    }, 'publish-key')

    const [, init] = lastRequest()
    const headers = new Headers(init.headers)
    expect(init.method).toBe('POST')
    expect(headers.get('Idempotency-Key')).toBe('publish-key')
    expect(JSON.parse(String(init.body))).toEqual({
      version: '1.2.0',
      draftRevision: 7,
    })
  })

  it('archives and restores through the status endpoint', async () => {
    await collectionApi.setStatus(
      'opensource',
      'superpowers',
      'ARCHIVED',
      'superseded',
    )

    const [url, init] = lastRequest()
    expect(url).toBe('/api/web/collections/opensource/superpowers/status')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(String(init.body))).toEqual({
      status: 'ARCHIVED',
      reason: 'superseded',
    })
  })
})

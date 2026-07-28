import { beforeEach, describe, expect, it, vi } from 'vitest'

const { list, detail } = vi.hoisted(() => ({
  list: vi.fn(),
  detail: vi.fn(),
}))

vi.mock('./api', () => ({
  collectionApi: {
    list,
    detail,
  },
}))

vi.mock('@/i18n/config', () => ({
  default: {
    resolvedLanguage: 'en',
    language: 'en',
  },
}))

import {
  collectionDetailQueryOptions,
  collectionListQueryOptions,
  invalidateCollectionQueries,
} from './use-collections'

beforeEach(() => {
  list.mockReset()
  detail.mockReset()
})

describe('collection query options', () => {
  it('builds a disabled namespace query without changing its key', async () => {
    list.mockResolvedValue({ items: [], total: 0 })
    const options = collectionListQueryOptions('opensource', false)

    expect(options.enabled).toBe(false)
    expect(options.queryKey).toEqual([
      'collections',
      'namespace',
      'opensource',
      'en',
    ])
    await options.queryFn()
    expect(list).toHaveBeenCalledWith('opensource')
  })

  it('builds an exact detail query and disables incomplete coordinates', async () => {
    detail.mockResolvedValue({ collectionId: 1 })
    const options = collectionDetailQueryOptions(
      'opensource',
      'superpowers',
      true,
    )

    expect(options.enabled).toBe(true)
    expect(options.queryKey).toEqual([
      'collections',
      'detail',
      'opensource',
      'superpowers',
      'en',
    ])
    await options.queryFn()
    expect(detail).toHaveBeenCalledWith('opensource', 'superpowers')
    expect(collectionDetailQueryOptions('', 'superpowers', true).enabled).toBe(false)
  })
})

describe('invalidateCollectionQueries', () => {
  it('invalidates the namespace list and exact detail after a mutation', async () => {
    const invalidateQueries = vi.fn().mockResolvedValue(undefined)

    await invalidateCollectionQueries(
      { invalidateQueries },
      'opensource',
      'superpowers',
    )

    expect(invalidateQueries).toHaveBeenNthCalledWith(1, {
      queryKey: ['collections', 'namespace', 'opensource', 'en'],
    })
    expect(invalidateQueries).toHaveBeenNthCalledWith(2, {
      queryKey: ['collections', 'detail', 'opensource', 'superpowers', 'en'],
    })
  })
})

import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import zh from './locales/zh.json'
import zhTW from './locales/zh-TW.json'

function paths(value: unknown, prefix = ''): string[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return [prefix]
  }
  return Object.entries(value).flatMap(([key, child]) =>
    paths(child, prefix ? `${prefix}.${key}` : key),
  )
}

describe('collection locale parity', () => {
  it('keeps the collection key tree aligned across all supported locales', () => {
    const collectionPaths = (locale: unknown) =>
      paths(locale).filter(
        (key) =>
          key.startsWith('collection') ||
          key.startsWith('repositoryImport') ||
          key.startsWith('namespace.collections') ||
          key.startsWith('namespace.collection'),
      )

    expect(collectionPaths(en)).toContain('collectionAdmin.title')
    expect(collectionPaths(en)).toContain('repositoryImport.open')
    expect(collectionPaths(zh).sort()).toEqual(collectionPaths(en).sort())
    expect(collectionPaths(zhTW).sort()).toEqual(collectionPaths(en).sort())
  })
})

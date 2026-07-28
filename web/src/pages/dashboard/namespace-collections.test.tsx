import { describe, expect, it } from 'vitest'

import {
  canCreateCollection,
  isValidCollectionSlug,
} from './namespace-collections'

describe('namespace collection curator policy', () => {
  it('allows namespace OWNER/ADMIN and global skill curators', () => {
    expect(canCreateCollection('OWNER', [])).toBe(true)
    expect(canCreateCollection('ADMIN', [])).toBe(true)
    expect(canCreateCollection('MEMBER', ['SKILL_ADMIN'])).toBe(true)
    expect(canCreateCollection(undefined, ['SUPER_ADMIN'])).toBe(true)
  })

  it('does not give collection ownership to ordinary members', () => {
    expect(canCreateCollection('MEMBER', [])).toBe(false)
    expect(canCreateCollection(undefined, [])).toBe(false)
  })

  it('accepts stable collection slugs only', () => {
    expect(isValidCollectionSlug('superpowers-core')).toBe(true)
    expect(isValidCollectionSlug('../admin')).toBe(false)
    expect(isValidCollectionSlug('Bad Name')).toBe(false)
  })
})

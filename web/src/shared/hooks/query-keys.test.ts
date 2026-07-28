import { describe, expect, it, vi } from 'vitest'

vi.mock('@/i18n/config', () => ({
  default: {
    resolvedLanguage: 'en',
    language: 'en',
  },
}))

import {
  getI18nCacheKey,
  getSkillDetailQueryKey,
  getVisibleLabelsQueryKey,
  getSkillLabelsQueryKey,
  getAdminLabelDefinitionsQueryKey,
  getCollectionDetailQueryKey,
  getCollectionListQueryKey,
} from './query-keys'

describe('getI18nCacheKey', () => {
  it('returns the resolved language', () => {
    expect(getI18nCacheKey()).toBe('en')
  })
})

describe('getSkillDetailQueryKey', () => {
  it('returns a tuple with skills, namespace, slug, and language', () => {
    const key = getSkillDetailQueryKey('team-ai', 'my-skill')
    expect(key).toEqual(['skills', 'team-ai', 'my-skill', 'en'])
  })
})

describe('getVisibleLabelsQueryKey', () => {
  it('returns a tuple with labels, visible, and language', () => {
    expect(getVisibleLabelsQueryKey()).toEqual(['labels', 'visible', 'en'])
  })
})

describe('getSkillLabelsQueryKey', () => {
  it('returns a tuple with labels, skill, namespace, slug, and language', () => {
    const key = getSkillLabelsQueryKey('team-ai', 'my-skill')
    expect(key).toEqual(['labels', 'skill', 'team-ai', 'my-skill', 'en'])
  })
})

describe('getAdminLabelDefinitionsQueryKey', () => {
  it('returns a tuple with labels, admin, and language', () => {
    expect(getAdminLabelDefinitionsQueryKey()).toEqual(['labels', 'admin', 'en'])
  })
})

describe('collection query keys', () => {
  it('uses a collection-specific localized namespace list key', () => {
    expect(getCollectionListQueryKey('opensource')).toEqual([
      'collections',
      'namespace',
      'opensource',
      'en',
    ])
  })

  it('uses a collection-specific localized detail key', () => {
    expect(getCollectionDetailQueryKey('opensource', 'superpowers')).toEqual([
      'collections',
      'detail',
      'opensource',
      'superpowers',
      'en',
    ])
  })
})

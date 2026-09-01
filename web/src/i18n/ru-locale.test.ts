import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import ru from './locales/ru.json'

function leafKeys(value: unknown, prefix = ''): string[] {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
      leafKeys(child, prefix ? `${prefix}.${key}` : key),
    )
  }
  return [prefix]
}

function leafValue(value: unknown, key: string): string {
  let cursor = value
  for (const part of key.split('.')) {
    cursor = (cursor as Record<string, unknown>)[part]
  }
  return String(cursor)
}

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{\{[^}]+\}\}/g)].map((match) => match[0]).sort()
}

describe('russian locale', () => {
  it('mirrors the current Python-fork English key tree', () => {
    expect(leafKeys(ru).sort()).toEqual(leafKeys(en).sort())
  })

  it('preserves interpolation placeholders', () => {
    const mismatches = leafKeys(en).filter((key) => (
      placeholders(leafValue(en, key)).join()
      !== placeholders(leafValue(ru, key)).join()
    ))

    expect(mismatches).toEqual([])
  })

  it('translates core and local-fork feature labels', () => {
    expect(ru.nav.home).not.toBe(en.nav.home)
    expect(ru.login.title).not.toBe(en.login.title)
    expect(ru.installSkills.title).not.toBe(en.installSkills.title)
    expect(ru.namespaceAnalytics.title).not.toBe(en.namespaceAnalytics.title)
    expect(ru.servicePrincipals.title).not.toBe(en.servicePrincipals.title)
    expect(ru.playground.title).not.toBe(en.playground.title)
  })
})

import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import zh from './locales/zh.json'
import zhTw from './locales/zh-TW.json'

function keys(value: unknown, prefix = ''): string[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [prefix]
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key))
}

describe('admin namespace locale contract', () => {
  it('keeps English, Simplified Chinese and Traditional Chinese keys aligned', () => {
    expect(keys(zh.adminNamespaces).sort()).toEqual(keys(en.adminNamespaces).sort())
    expect(keys(zhTw.adminNamespaces).sort()).toEqual(keys(en.adminNamespaces).sort())
  })

  it('includes the super-admin menu item in every locale', () => {
    expect(en.user.menu.namespaceManagement).toBeTruthy()
    expect(zh.user.menu.namespaceManagement).toBeTruthy()
    expect(zhTw.user.menu.namespaceManagement).toBeTruthy()
  })
})

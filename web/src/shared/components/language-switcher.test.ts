import { describe, expect, it } from 'vitest'
import * as mod from './language-switcher'

/**
 * LanguageSwitcher is a React component that renders a dropdown to switch
 * between Chinese and English using i18next.
 * All logic depends on i18next hooks and Radix DropdownMenu primitives.
 * There are no exported pure helpers or constants to test here.
 *
 * We verify the module shape so downstream consumers break fast
 * if the export contract changes.
 */
describe('language-switcher module exports', () => {
  it('exports the LanguageSwitcher component', () => {
    expect(mod.LanguageSwitcher).toBeTypeOf('function')
  })

  it('keeps regional chinese language codes distinct', () => {
    expect(mod.resolveSupportedLanguageCode('zh-TW')).toBe('zh-TW')
    expect(mod.resolveSupportedLanguageCode('zh-Hant')).toBe('zh-TW')
    expect(mod.resolveSupportedLanguageCode('zh-HK')).toBe('zh-TW')
    expect(mod.resolveSupportedLanguageCode('zh-MO')).toBe('zh-TW')
    expect(mod.resolveSupportedLanguageCode('zh-CN')).toBe('zh')
    expect(mod.resolveSupportedLanguageCode('en-US')).toBe('en')
  })

  it('offers traditional chinese, simplified chinese, and english', () => {
    expect(mod.languages.map((language) => language.code)).toEqual(['zh-TW', 'zh', 'en'])
    expect(mod.languages.map((language) => language.name)).toEqual(['繁體中文', '简体中文', 'English'])
  })
})

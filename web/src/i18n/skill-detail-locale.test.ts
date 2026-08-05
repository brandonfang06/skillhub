import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import zh from './locales/zh.json'
import zhTW from './locales/zh-TW.json'

describe('skill detail lifecycle locales', () => {
  it('defines the unarchive label in both locales', () => {
    expect(zh.skillDetail.unarchiveSkill).toBe('恢复技能')
    expect(en.skillDetail.unarchiveSkill).toBe('Restore Skill')
  })

  it('defines anonymous protected-content guidance in every supported locale', () => {
    for (const locale of [en, zh, zhTW]) {
      expect(locale.skillDetail.readmeLoginRequiredTitle).toBeTruthy()
      expect(locale.skillDetail.readmeLoginRequiredDescription).toBeTruthy()
      expect(locale.skillDetail.signInToView).toBeTruthy()
      expect(locale.skillDetail.filesLoginRequired).toBeTruthy()
      expect(locale.skillDetail.sessionExpiredTitle).toBeTruthy()
      expect(locale.skillDetail.sessionExpiredDescription).toBeTruthy()
      expect(locale.skillDetail.signInAgain).toBeTruthy()
    }
    expect(zhTW.skillDetail.signInToView).toBe('登入查看')
  })
})

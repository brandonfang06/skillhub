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

  it('defines version attribution labels in every supported locale', () => {
    for (const locale of [en, zh, zhTW]) {
      expect(locale.skillDetail.versionAttributionTitle).toBeTruthy()
      expect(locale.skillDetail.submittedBy).toBeTruthy()
      expect(locale.skillDetail.submittedAt).toBeTruthy()
      expect(locale.skillDetail.importedBy).toBeTruthy()
      expect(locale.skillDetail.importedAt).toBeTruthy()
    }

    expect(en.skillDetail.submittedBy).toBe('Submitted by')
    expect(zh.skillDetail.importedBy).toBe('导入者')
    expect(zhTW.skillDetail.importedBy).toBe('匯入者')
  })
})

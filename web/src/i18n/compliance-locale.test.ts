import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import zh from './locales/zh.json'
import zhTW from './locales/zh-TW.json'

describe('compliance locales', () => {
  it('provides publisher-claim and review-diff strings in every supported locale', () => {
    for (const locale of [en, zh, zhTW]) {
      expect(locale.common.expand).toBeTruthy()
      expect(locale.common.collapse).toBeTruthy()
      expect(locale.compliance.title).toBeTruthy()
      expect(locale.compliance.badgeLabel).toBeTruthy()
      expect(locale.compliance.publisherClaimNotice).toBeTruthy()
      expect(locale.compliance.notCertification).toBeTruthy()
      expect(locale.review.complianceDiffTitle).toBeTruthy()
      expect(locale.review.complianceDiffClaimNotice).toBeTruthy()
      expect(locale.review.complianceDiffAdded).toBeTruthy()
      expect(locale.review.complianceDiffRemoved).toBeTruthy()
      expect(locale.review.complianceDiffModified).toBeTruthy()
    }
  })

  it('uses explicit unverified-claim language', () => {
    expect(en.compliance.publisherClaimNotice).toContain('publisher')
    expect(en.compliance.notCertification).toContain('not verified')
    expect(zh.compliance.notCertification).toContain('未经平台验证')
    expect(zhTW.compliance.notCertification).toContain('未經平台驗證')
  })
})

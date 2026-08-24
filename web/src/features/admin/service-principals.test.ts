import { describe, expect, it } from 'vitest'
import en from '@/i18n/locales/en.json'
import zhTW from '@/i18n/locales/zh-TW.json'
import zh from '@/i18n/locales/zh.json'
import { servicePrincipalsUrl, serviceTokensUrl } from './service-principals'

describe('service principal admin API paths', () => {
  it('uses relative base-aware paths and safely encodes ids', () => {
    expect(servicePrincipalsUrl()).toBe('/api/v1/admin/service-principals?page=0&size=100')
    expect(serviceTokensUrl('svc/importer')).toBe('/api/v1/admin/service-principals/svc%2Fimporter/tokens')
  })

  it('provides service account expiry actions in all supported languages', () => {
    for (const locale of [en, zh, zhTW]) {
      expect(locale.dialog.cancel).toBeTruthy()
      expect(locale.dialog.close).toBeTruthy()
      expect(locale.servicePrincipals.create).toBeTruthy()
      expect(locale.servicePrincipals.expiryLabel).toBeTruthy()
      expect(locale.servicePrincipals.expiryHint).toBeTruthy()
      expect(locale.servicePrincipals.expiryRequired).toBeTruthy()
      expect(locale.servicePrincipals.expiryRange).toBeTruthy()
      expect(locale.servicePrincipals.neverExpires).toBeTruthy()
      expect(locale.servicePrincipals.neverExpiresWarning).toBeTruthy()
      expect(locale.servicePrincipals.rotateToken).toBeTruthy()
      expect(locale.servicePrincipals.revokeToken).toBeTruthy()
    }
  })
})

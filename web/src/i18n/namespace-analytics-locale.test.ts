import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import zh from './locales/zh.json'
import zhTW from './locales/zh-TW.json'

const REQUIRED_KEYS = [
  'title',
  'subtitle',
  'retentionNote',
  'summaryNamespaces',
  'summaryMaintainers',
  'summarySkills',
  'summaryLifetimeDownloads',
  'summaryPeriodDownloads',
  'periodRange',
  'searchPlaceholder',
  'namespaceTypeAll',
  'namespaceTypeTeam',
  'namespaceTypeGlobal',
  'namespaceStatusAll',
  'namespaceStatusActive',
  'namespaceStatusFrozen',
  'namespaceStatusArchived',
  'period7Days',
  'period30Days',
  'period90Days',
  'periodCustom',
  'sourceAll',
  'sourceWeb',
  'sourceCli',
  'sourceApi',
  'exportCsv',
  'exportingCsv',
  'exportSuccess',
  'exportError',
  'exportTruncatedTitle',
  'exportTruncatedDescription',
  'clearFilters',
  'retry',
  'emptyTitle',
  'emptyDescription',
  'colNamespace',
  'colMaintainers',
  'colSkills',
  'colLifetimeDownloads',
  'colPeriodDownloads',
  'viewEvents',
  'previousPage',
  'nextPage',
] as const

describe('namespace analytics locale contract', () => {
  it.each([
    ['en', en],
    ['zh', zh],
    ['zh-TW', zhTW],
  ] as const)('defines every page key in %s', (_name, locale) => {
    for (const key of REQUIRED_KEYS) {
      expect(locale.namespaceAnalytics[key]).toBeTruthy()
    }
    expect(locale.user.menu.namespaceAnalytics).toBeTruthy()
  })

  it('uses the approved Traditional Chinese analytics wording', () => {
    expect(zhTW.namespaceAnalytics.summaryMaintainers).toBe('維護者')
    expect(zhTW.namespaceAnalytics.summarySkills).toBe('Catalog Skills')
    expect(zhTW.namespaceAnalytics.summaryLifetimeDownloads).toBe('累計下載')
    expect(zhTW.namespaceAnalytics.summaryPeriodDownloads).toBe('期間下載')
  })
})

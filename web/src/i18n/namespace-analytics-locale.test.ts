import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import zh from './locales/zh.json'
import zhTW from './locales/zh-TW.json'

const REQUIRED_KEYS = [
  'title',
  'subtitle',
  'catalogView',
  'securityView',
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

const REQUIRED_SECURITY_KEYS = [
  'subtitle',
  'summaryNamespaces',
  'summarySkills',
  'summaryVersions',
  'summaryFindings',
  'severityAll',
  'severityCritical',
  'severityHigh',
  'severityMedium',
  'severityLow',
  'severityInfo',
  'severityUnclassified',
  'searchPlaceholder',
  'visibilityAll',
  'versionStatusAll',
  'moreFilters',
  'skillStatusAll',
  'hiddenAll',
  'visibleOnly',
  'hiddenOnly',
  'scannerAll',
  'hidden',
  'owner',
  'findingInstances',
  'colAffectedSkills',
  'colAffectedVersions',
  'colMaxSeverity',
  'colDistribution',
  'colFindings',
  'colLatestScan',
  'colVersion',
  'colVersionStatus',
  'colScanners',
  'colSeverity',
  'expandNamespace',
  'collapseNamespace',
  'errorTitle',
  'errorDescription',
  'emptyTitle',
  'emptyDescription',
  'skillLoadError',
  'totalSkills',
  'previousSkillsPage',
  'nextSkillsPage',
  'totalNamespaces',
  'detailDescription',
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
    for (const key of REQUIRED_SECURITY_KEYS) {
      expect(locale.namespaceSecurity[key]).toBeTruthy()
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

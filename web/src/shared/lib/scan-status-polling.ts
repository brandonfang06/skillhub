const SCAN_REFETCH_INTERVAL_MS = 3_000

type StatusRecord = {
  status?: unknown
  headlineVersion?: unknown
  ownerPreviewVersion?: unknown
  publishedVersion?: unknown
  versions?: unknown
  items?: unknown
}

function hasScanningVersion(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some(hasScanningVersion)
  }
  if (!value || typeof value !== 'object') {
    return false
  }

  const record = value as StatusRecord
  return record.status === 'SCANNING'
    || hasScanningVersion(record.headlineVersion)
    || hasScanningVersion(record.ownerPreviewVersion)
    || hasScanningVersion(record.publishedVersion)
    || hasScanningVersion(record.versions)
    || hasScanningVersion(record.items)
}

export function scanStatusRefetchInterval(data: unknown): number | false {
  return hasScanningVersion(data) ? SCAN_REFETCH_INTERVAL_MS : false
}

export function securityAuditRefetchInterval(data: unknown, versionStatus?: string): number | false {
  if (versionStatus === 'SCAN_FAILED') {
    return false
  }
  if (versionStatus === 'SCANNING') {
    return SCAN_REFETCH_INTERVAL_MS
  }
  if (!Array.isArray(data)) {
    return false
  }
  return data.some((audit) => (
    audit !== null
    && typeof audit === 'object'
    && 'scannedAt' in audit
    && audit.scannedAt === null
  )) ? SCAN_REFETCH_INTERVAL_MS : false
}

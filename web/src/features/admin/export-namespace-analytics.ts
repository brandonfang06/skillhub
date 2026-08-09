import { buildApiUrl } from '@/api/client'
import type { NamespaceAnalyticsParams } from '@/api/types'
import { buildNamespaceAnalyticsSearchParams } from './use-namespace-analytics'

const DEFAULT_FILENAME = 'skillhub-namespace-analytics.csv'
const DEFAULT_ROW_LIMIT = 10_000

export interface NamespaceAnalyticsExportResult {
  truncated: boolean
  rowLimit: number
}

function responseErrorMessage(value: unknown, status: number): string {
  if (typeof value === 'object' && value !== null) {
    if ('msg' in value && typeof value.msg === 'string' && value.msg) return value.msg
    if ('detail' in value && typeof value.detail === 'string' && value.detail) return value.detail
  }
  return `HTTP ${status}`
}

async function failedResponseMessage(response: Response): Promise<string> {
  try {
    return responseErrorMessage(await response.json(), response.status)
  } catch {
    return `HTTP ${response.status}`
  }
}

function downloadFilename(contentDisposition: string | null): string {
  const match = contentDisposition?.match(/filename="?([^";]+)"?/i)
  if (!match) return DEFAULT_FILENAME
  const sanitized = match[1].trim().replace(/[\\/:*?"<>|]/g, '_')
  return sanitized || DEFAULT_FILENAME
}

function saveBlob(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  try {
    link.click()
  } finally {
    link.remove()
    URL.revokeObjectURL(objectUrl)
  }
}

export function buildNamespaceAnalyticsCsvUrl(params: NamespaceAnalyticsParams): string {
  const searchParams = buildNamespaceAnalyticsSearchParams(params, { includePagination: false })
  return buildApiUrl(`/api/v1/admin/namespace-analytics.csv?${searchParams.toString()}`)
}

export async function exportNamespaceAnalyticsCsv(
  params: NamespaceAnalyticsParams,
): Promise<NamespaceAnalyticsExportResult> {
  const response = await fetch(buildNamespaceAnalyticsCsvUrl(params), {
    credentials: 'same-origin',
    headers: { Accept: 'text/csv' },
  })
  if (!response.ok) {
    throw new Error(await failedResponseMessage(response))
  }

  const blob = await response.blob()
  saveBlob(blob, downloadFilename(response.headers.get('Content-Disposition')))
  const parsedRowLimit = Number(response.headers.get('X-SkillHub-Export-Row-Limit'))
  return {
    truncated: response.headers.get('X-SkillHub-Export-Truncated')?.toLowerCase() === 'true',
    rowLimit: Number.isInteger(parsedRowLimit) && parsedRowLimit > 0 ? parsedRowLimit : DEFAULT_ROW_LIMIT,
  }
}

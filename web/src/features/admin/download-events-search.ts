export type DownloadEventSource = 'web' | 'cli' | 'api'

export interface DownloadEventsSearch {
  namespace?: string
  slug?: string
  version?: string
  userId?: string
  source?: DownloadEventSource
  startTime?: string
  endTime?: string
}

const SOURCES = ['web', 'cli', 'api'] as const

function optionalText(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  return value.trim() || undefined
}

function optionalInstant(value: unknown): string | undefined {
  if (typeof value !== 'string' || Number.isNaN(new Date(value).getTime())) {
    return undefined
  }
  return value
}

export function parseDownloadEventsSearch(search: Record<string, unknown>): DownloadEventsSearch {
  const source = typeof search.source === 'string' && SOURCES.includes(search.source as DownloadEventSource)
    ? search.source as DownloadEventSource
    : undefined
  return {
    namespace: optionalText(search.namespace),
    slug: optionalText(search.slug),
    version: optionalText(search.version),
    userId: optionalText(search.userId),
    source,
    startTime: optionalInstant(search.startTime),
    endTime: optionalInstant(search.endTime),
  }
}

import { EXIT } from './constants'
import { CliError } from './errors'

const COLLECTION_SEGMENT = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/

export interface ParsedCollectionName {
  namespace: string
  slug: string
}

export function isSafeCollectionSegment(value: string): boolean {
  return (
    value.length > 0 &&
    value.length <= 128 &&
    COLLECTION_SEGMENT.test(value) &&
    !value.includes('--')
  )
}

export function parseCollectionName(value: string): ParsedCollectionName {
  const match = /^@([^/]+)\/([^/]+)$/.exec(value.trim())
  if (
    !match ||
    !isSafeCollectionSegment(match[1]!) ||
    !isSafeCollectionSegment(match[2]!)
  ) {
    throw new CliError(
      'collection must use @namespace/collection',
      EXIT.usage
    )
  }
  return {
    namespace: match[1]!,
    slug: match[2]!
  }
}

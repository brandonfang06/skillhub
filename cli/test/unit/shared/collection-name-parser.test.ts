import { describe, expect, test } from 'bun:test'
import {
  isSafeCollectionSegment,
  parseCollectionName
} from '../../../src/shared/collection-name-parser'
import { CliError } from '../../../src/shared/errors'
import { EXIT } from '../../../src/shared/constants'

describe('parseCollectionName', () => {
  test('parses the required scoped collection coordinate', () => {
    expect(parseCollectionName('@opensource/superpowers')).toEqual({
      namespace: 'opensource',
      slug: 'superpowers'
    })
  })

  test.each([
    'superpowers',
    '@opensource',
    '@opensource/',
    '@/superpowers',
    '@opensource/a/b',
    '@../escape',
    '@opensource/..',
    '@OpenSource/superpowers',
    '@opensource/super--powers'
  ])('rejects unsafe coordinate %s', (coordinate) => {
    try {
      parseCollectionName(coordinate)
      throw new Error('expected parser failure')
    } catch (error) {
      expect(error).toBeInstanceOf(CliError)
      expect(error).toHaveProperty('message', 'collection must use @namespace/collection')
      expect(error).toHaveProperty('exitCode', EXIT.usage)
    }
  })
})

describe('isSafeCollectionSegment', () => {
  test('accepts server-compatible namespace and slug segments', () => {
    expect(isSafeCollectionSegment('opensource')).toBe(true)
    expect(isSafeCollectionSegment('super-powers-2')).toBe(true)
  })

  test.each(['', '.', '..', 'a/b', 'a\\b', '-leading', 'trailing-', 'a--b'])(
    'rejects unsafe segment %s',
    (segment) => {
      expect(isSafeCollectionSegment(segment)).toBe(false)
    }
  )

  test('rejects a segment longer than the server limit', () => {
    expect(isSafeCollectionSegment('a'.repeat(129))).toBe(false)
  })
})

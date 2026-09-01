import { describe, expect, it } from 'vitest'
import { formatRelativeTime } from './format-relative-time'

const NOW = Date.parse('2026-09-01T12:00:00Z')

function expected(
  locale: string,
  value: number,
  unit: Intl.RelativeTimeFormatUnit,
) {
  return new Intl.RelativeTimeFormat(locale, {
    numeric: 'auto',
    style: 'narrow',
  }).format(value, unit)
}

describe('formatRelativeTime', () => {
  it('selects second, minute, hour, and day units at stable boundaries', () => {
    expect(formatRelativeTime('2026-09-01T11:59:40Z', 'en', NOW)).toBe(
      expected('en', 0, 'second'),
    )
    expect(formatRelativeTime('2026-09-01T11:55:00Z', 'en', NOW)).toBe(
      expected('en', -5, 'minute'),
    )
    expect(formatRelativeTime('2026-09-01T10:00:00Z', 'en', NOW)).toBe(
      expected('en', -2, 'hour'),
    )
    expect(formatRelativeTime('2026-08-29T12:00:00Z', 'en', NOW)).toBe(
      expected('en', -3, 'day'),
    )
  })

  it.each([
    ['zh', 'zh-CN'],
    ['zh-TW', 'zh-TW'],
    ['ru', 'ru-RU'],
  ])('uses the expected ICU locale for %s', (language, locale) => {
    expect(formatRelativeTime('2026-09-01T11:55:00Z', language, NOW)).toBe(
      expected(locale, -5, 'minute'),
    )
  })

  it('formats future timestamps without treating them as just now', () => {
    expect(formatRelativeTime('2026-09-01T12:05:00Z', 'en', NOW)).toBe(
      expected('en', 5, 'minute'),
    )
  })

  it('falls back to an absolute localized date after 30 days', () => {
    const date = new Date('2026-07-01T12:00:00Z')
    expect(formatRelativeTime(date.toISOString(), 'ru', NOW)).toBe(
      new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(date),
    )
  })

  it('returns an empty string for an invalid timestamp', () => {
    expect(formatRelativeTime('not-a-date', 'en', NOW)).toBe('')
  })
})

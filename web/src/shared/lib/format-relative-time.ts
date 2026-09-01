function relativeTimeLocale(language: string): string {
  const normalized = language.trim().toLowerCase()
  if (normalized === 'zh-tw' || normalized.startsWith('zh-hant')) return 'zh-TW'
  if (normalized.startsWith('zh')) return 'zh-CN'
  if (normalized.startsWith('ru')) return 'ru-RU'
  return 'en'
}

/** Formats a timestamp as one complete localized phrase such as "5m ago". */
export function formatRelativeTime(
  dateString: string,
  language: string,
  now = Date.now(),
): string {
  const timestamp = Date.parse(dateString)
  if (!Number.isFinite(timestamp)) return ''

  const locale = relativeTimeLocale(language)
  const delta = timestamp - now
  const absoluteDelta = Math.abs(delta)
  const formatter = new Intl.RelativeTimeFormat(locale, {
    numeric: 'auto',
    style: 'narrow',
  })

  if (absoluteDelta < 60_000) return formatter.format(0, 'second')
  if (absoluteDelta < 3_600_000) {
    return formatter.format(Math.round(delta / 60_000), 'minute')
  }
  if (absoluteDelta < 86_400_000) {
    return formatter.format(Math.round(delta / 3_600_000), 'hour')
  }
  if (absoluteDelta < 30 * 86_400_000) {
    return formatter.format(Math.round(delta / 86_400_000), 'day')
  }

  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(
    new Date(timestamp),
  )
}

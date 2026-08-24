export const MAX_SERVICE_TOKEN_YEARS = 3

const DEFAULT_SERVICE_TOKEN_DAYS = 90
const DATE_INPUT_PATTERN = /^\d{4}-\d{2}-\d{2}$/

export type ServiceTokenExpiryMode = 'expires' | 'never'
export type ServiceTokenExpiryError = 'required' | 'range' | null

export interface ServiceTokenExpiryBounds {
  min: string
  max: string
  defaultValue: string
}

function formatUtcDate(value: Date): string {
  return value.toISOString().slice(0, 10)
}

function addUtcCalendarYears(value: Date, years: number): Date {
  const year = value.getUTCFullYear() + years
  const month = value.getUTCMonth()
  const day = value.getUTCDate()
  const anniversary = new Date(Date.UTC(year, month, day))

  if (anniversary.getUTCMonth() !== month) {
    return new Date(Date.UTC(year, month + 1, 0))
  }
  return anniversary
}

export function serviceTokenExpiryBounds(now: Date): ServiceTokenExpiryBounds {
  const defaultExpiry = new Date(now)
  defaultExpiry.setUTCDate(defaultExpiry.getUTCDate() + DEFAULT_SERVICE_TOKEN_DAYS)

  return {
    min: formatUtcDate(now),
    max: formatUtcDate(addUtcCalendarYears(now, MAX_SERVICE_TOKEN_YEARS)),
    defaultValue: formatUtcDate(defaultExpiry),
  }
}

export function validateServiceTokenExpiryDate(
  value: string,
  bounds: ServiceTokenExpiryBounds,
  mode: ServiceTokenExpiryMode,
): ServiceTokenExpiryError {
  if (mode === 'never') {
    return null
  }
  if (!value) {
    return 'required'
  }
  if (!DATE_INPUT_PATTERN.test(value)) {
    return 'range'
  }

  const parsed = new Date(`${value}T00:00:00.000Z`)
  if (Number.isNaN(parsed.getTime()) || formatUtcDate(parsed) !== value) {
    return 'range'
  }
  if (value < bounds.min || value > bounds.max) {
    return 'range'
  }
  return null
}

export function serviceTokenExpiryValue(
  value: string,
  mode: ServiceTokenExpiryMode,
): string | null {
  if (mode === 'never') {
    return null
  }
  return new Date(`${value}T23:59:59.000Z`).toISOString()
}

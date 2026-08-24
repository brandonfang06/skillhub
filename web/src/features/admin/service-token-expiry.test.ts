import { describe, expect, it } from 'vitest'
import {
  serviceTokenExpiryBounds,
  serviceTokenExpiryValue,
  validateServiceTokenExpiryDate,
} from './service-token-expiry'

describe('service token expiry', () => {
  it('calculates UTC date bounds with a 90-day default and three-year maximum', () => {
    expect(serviceTokenExpiryBounds(new Date('2026-08-24T08:00:00Z'))).toEqual({
      min: '2026-08-24',
      max: '2029-08-24',
      defaultValue: '2026-11-22',
    })
  })

  it('uses February 28 when a leap-day anniversary is not a leap year', () => {
    expect(serviceTokenExpiryBounds(new Date('2028-02-29T12:00:00Z')).max).toBe('2031-02-28')
  })

  it('validates expiring dates but accepts an explicit never mode', () => {
    const bounds = serviceTokenExpiryBounds(new Date('2026-08-24T08:00:00Z'))

    expect(validateServiceTokenExpiryDate('', bounds, 'expires')).toBe('required')
    expect(validateServiceTokenExpiryDate('2026-02-30', bounds, 'expires')).toBe('range')
    expect(validateServiceTokenExpiryDate('2029-08-25', bounds, 'expires')).toBe('range')
    expect(validateServiceTokenExpiryDate('', bounds, 'never')).toBeNull()
  })

  it('maps an expiring selection to an instant and never to explicit null', () => {
    expect(serviceTokenExpiryValue('2029-08-24', 'expires')).toBe('2029-08-24T23:59:59.000Z')
    expect(serviceTokenExpiryValue('', 'never')).toBeNull()
  })
})

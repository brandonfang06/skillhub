import { describe, expect, it } from 'vitest'
import { servicePrincipalsUrl, serviceTokensUrl } from './service-principals'

describe('service principal admin API paths', () => {
  it('uses relative base-aware paths and safely encodes ids', () => {
    expect(servicePrincipalsUrl()).toBe('/api/v1/admin/service-principals?page=0&size=100')
    expect(serviceTokensUrl('svc/importer')).toBe('/api/v1/admin/service-principals/svc%2Fimporter/tokens')
  })
})

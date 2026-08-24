import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { ServiceTokenForm, ServiceTokenRow } from './service-token-controls'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { date?: string }) => values?.date ? `${key}:${values.date}` : key,
  }),
}))

describe('service token controls', () => {
  it('renders the three-year date bound for expiring tokens', () => {
    const html = renderToStaticMarkup(
      <ServiceTokenForm
        tokenName="production-importer"
        expiryMode="expires"
        expiresOn="2029-08-25"
        minExpiresOn="2026-08-24"
        maxExpiresOn="2029-08-24"
        expiryError="servicePrincipals.expiryRange"
        isPending={false}
        disabled
        onTokenNameChange={vi.fn()}
        onExpiryModeChange={vi.fn()}
        onExpiresOnChange={vi.fn()}
        onCreate={vi.fn()}
      />,
    )

    expect(html).toContain('maxLength="100"')
    expect(html).toContain('min="2026-08-24"')
    expect(html).toContain('max="2029-08-24"')
    expect(html).toContain('aria-invalid="true"')
    expect(html).toContain('servicePrincipals.expiryRange')
  })

  it('requires an explicit never selection and displays its warning', () => {
    const html = renderToStaticMarkup(
      <ServiceTokenForm
        tokenName="persistent-importer"
        expiryMode="never"
        expiresOn=""
        minExpiresOn="2026-08-24"
        maxExpiresOn="2029-08-24"
        expiryError={null}
        isPending={false}
        disabled={false}
        onTokenNameChange={vi.fn()}
        onExpiryModeChange={vi.fn()}
        onExpiresOnChange={vi.fn()}
        onCreate={vi.fn()}
      />,
    )

    expect(html).toMatch(/type="checkbox"[^>]*checked=""/)
    expect(html).toContain('servicePrincipals.neverExpires')
    expect(html).toContain('servicePrincipals.neverExpiresWarning')
    expect(html).toMatch(/type="date"[^>]*disabled=""/)
  })

  it('keeps a long never-expiring token readable without hiding its actions', () => {
    const longName = 'production-importer-for-the-company-wide-gitlab-automation-runner'
    const html = renderToStaticMarkup(
      <ServiceTokenRow
        token={{
          id: 7,
          servicePrincipalId: 'svc_1',
          name: longName,
          tokenPrefix: 'st_example',
          scopes: ['source:import'],
          createdAt: '2026-08-24T00:00:00Z',
          expiresAt: null,
          lastUsedAt: null,
          revokedAt: null,
        }}
        formattedExpiry="servicePrincipals.neverExpires"
        rotateDisabled
        revokeDisabled={false}
        onRotate={vi.fn()}
        onRevoke={vi.fn()}
      />,
    )

    expect(html).toContain(longName)
    expect(html).toContain('min-w-0')
    expect(html).toContain('break-words')
    expect(html).toContain('shrink-0')
    expect(html).toContain('servicePrincipals.neverExpires')
    expect(html).not.toMatch(/aria-label="servicePrincipals.revokeToken"[^>]*disabled=""/)
  })
})

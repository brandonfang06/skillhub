import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { VersionAttributionCard } from './version-attribution'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string) =>
      ({
        'skillDetail.versionAttributionTitle': 'Version attribution',
        'skillDetail.submittedBy': 'Submitted by',
        'skillDetail.submittedAt': 'Submitted at',
      })[key] ?? key,
  }),
}))

describe('VersionAttributionCard', () => {
  it('renders the native submitter without truncating a long display name', () => {
    const displayName = 'Bob Submitter With A Very Long Human Readable Display Name'
    const html = renderToStaticMarkup(
      <VersionAttributionCard
        attribution={{
          type: 'NATIVE_SUBMISSION',
          submittedBy: 'native-user',
          submittedByName: displayName,
          submittedAt: '2026-08-19T08:00:00Z',
        }}
      />,
    )

    expect(html).toContain('data-testid="version-attribution"')
    expect(html).toContain('Submitted by')
    expect(html).toContain(displayName)
    expect(html).toContain('break-words')
  })

  it('falls back to the stable user id when the display name is unavailable', () => {
    const html = renderToStaticMarkup(
      <VersionAttributionCard
        attribution={{
          type: 'NATIVE_SUBMISSION',
          submittedBy: 'native-user',
          submittedByName: null,
          submittedAt: '2026-08-19T08:00:00Z',
        }}
      />,
    )

    expect(html).toContain('native-user')
  })

  it('does not duplicate OSS or missing attribution outside source provenance', () => {
    expect(
      renderToStaticMarkup(
        <VersionAttributionCard
          attribution={{
            type: 'OSS_IMPORT',
            submittedBy: 'trigger-user',
            submittedByName: 'hcfange',
            submittedAt: '2026-08-19T08:00:00Z',
          }}
        />,
      ),
    ).toBe('')
    expect(renderToStaticMarkup(<VersionAttributionCard attribution={null} />)).toBe('')
  })
})

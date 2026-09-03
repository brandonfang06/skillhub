import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { SourceProvenanceCard } from './source-provenance'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string) =>
      ({
        'skillDetail.importedBy': 'Imported by',
        'skillDetail.importedAt': 'Imported at',
      })[key] ?? key,
  }),
}))

const provenance = {
  repositoryUrl: 'https://github.com/mattpocock/skills',
  repositoryRevisionSha: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  sourceRefType: 'TAG' as const,
  sourceRef: 'v1.2.0',
  sourcePath: 'skills/code-review',
  contentFingerprint: 'f'.repeat(64),
  browseUrl: 'https://github.com/mattpocock/skills/tree/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/skills/code-review',
}

const attribution = {
  type: 'OSS_IMPORT' as const,
  submittedBy: 'trigger-user',
  submittedByName: 'hcfange',
  submittedAt: '2026-08-19T08:00:00Z',
}

describe('SourceProvenanceCard', () => {
  it('renders source provenance without an external repository link', () => {
    const html = renderToStaticMarkup(
      <SourceProvenanceCard provenance={provenance} attribution={attribution} />,
    )

    expect(html).toContain('data-testid="source-provenance"')
    expect(html).toContain('tag: v1.2.0')
    expect(html).toContain('skills/code-review')
    expect(html).not.toContain(provenance.browseUrl)
    expect(html).not.toContain('href=')
    expect(html).toContain('Imported by')
    expect(html).toContain('hcfange')
  })

  it('does not render for native SkillHub versions', () => {
    expect(renderToStaticMarkup(<SourceProvenanceCard provenance={null} />)).toBe('')
  })
})

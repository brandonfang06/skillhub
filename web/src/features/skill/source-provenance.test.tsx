import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { SourceProvenanceCard } from './source-provenance'

const provenance = {
  repositoryUrl: 'https://github.com/mattpocock/skills',
  repositoryRevisionSha: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  sourceRefType: 'TAG' as const,
  sourceRef: 'v1.2.0',
  sourcePath: 'skills/code-review',
  contentFingerprint: 'f'.repeat(64),
  browseUrl: 'https://github.com/mattpocock/skills/tree/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/skills/code-review',
}

describe('SourceProvenanceCard', () => {
  it('renders an immutable source link, ref, and repository path', () => {
    const html = renderToStaticMarkup(<SourceProvenanceCard provenance={provenance} />)

    expect(html).toContain('data-testid="source-provenance"')
    expect(html).toContain('tag: v1.2.0')
    expect(html).toContain('skills/code-review')
    expect(html).toContain(`href="${provenance.browseUrl}"`)
    expect(html).toContain('target="_blank"')
  })

  it('does not render for native SkillHub versions', () => {
    expect(renderToStaticMarkup(<SourceProvenanceCard provenance={null} />)).toBe('')
  })
})

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { SkillVersion } from '@/api/types'
import {
  compareComplianceSnapshots,
  pickBaseVersion,
  ReviewComplianceDiffPanel,
} from './review-compliance-diff-panel'

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, number | string>) =>
        values?.count === undefined ? key : `${key}:${values.count}`,
    }),
  }
})

function createVersion(overrides: Partial<SkillVersion> = {}): SkillVersion {
  return {
    id: 1,
    version: '1.0.0',
    status: 'PUBLISHED',
    fileCount: 1,
    totalSize: 100,
    publishedAt: '2026-03-19T00:00:00Z',
    downloadAvailable: true,
    ...overrides,
  }
}

describe('compliance review semantics', () => {
  it('keys mappings by normalized standard/version/controlId and ignores evidence ordering', () => {
    const base = {
      schemaVersion: '1.0',
      digest: 'sha256:base',
      items: [{
        standard: ' SOC2 ', version: ' 2026 ', controlId: ' CC7.2 ', title: 'Monitor',
        evidence: [
          { type: 'external-url', url: 'https://b.test', sha256: 'b' },
          { type: 'packaged-file', path: 'evidence/a.md', sha256: 'a' },
        ],
      }],
    }
    const pending = {
      schemaVersion: '1.0',
      digest: 'sha256:pending',
      items: [{
        standard: 'soc2', version: '2026', controlId: 'CC7.2', title: 'Monitor',
        evidence: [
          { type: 'packaged-file', path: 'evidence/a.md', sha256: 'a' },
          { type: 'external-url', url: 'https://b.test', sha256: 'b' },
        ],
      }],
    }

    expect(compareComplianceSnapshots(base, pending)).toEqual({
      diffs: [], added: 0, removed: 0, modified: 0,
    })
  })

  it('reports added, removed, and modified declarations with evidence detail', () => {
    const diff = compareComplianceSnapshots(
      {
        items: [
          { standard: 'soc2', version: '2025', controlId: 'removed' },
          { standard: 'soc2', version: '2025', controlId: 'changed', title: 'Before' },
        ],
      },
      {
        items: [
          { standard: 'soc2', version: '2025', controlId: 'changed', title: 'After' },
          { standard: 'nist-csf', version: '2.0', controlId: 'added' },
        ],
      },
    )

    expect(diff.removed).toBe(1)
    expect(diff.modified).toBe(1)
    expect(diff.added).toBe(1)
    expect(diff.diffs.map((entry) => entry.kind)).toEqual(['removed', 'modified', 'added'])
  })

  it('picks the latest previous published version deterministically', () => {
    const versions = [
      createVersion({ id: 2, version: '1.1.0', publishedAt: 'invalid' }),
      createVersion({ id: 4, version: '1.2.0', publishedAt: 'invalid' }),
      createVersion({ id: 8, version: '2.0.0', status: 'PENDING_REVIEW' }),
      createVersion({ id: 3, version: '1.0.0', publishedAt: '2026-01-01T00:00:00Z' }),
    ]

    expect(pickBaseVersion(versions, '2.0.0')?.id).toBe(3)
    expect(pickBaseVersion(versions.slice(0, 3), '2.0.0')?.id).toBe(4)
    expect(pickBaseVersion([...versions.slice(0, 3)].reverse(), '2.0.0')?.id).toBe(4)
  })

  it('renders claims language, digest labels, and wrapping-safe evidence', () => {
    const html = renderToStaticMarkup(
      <ReviewComplianceDiffPanel
        baseVersion={createVersion({
          complianceSnapshot: {
            schemaVersion: '1.0', digest: 'sha256:base-digest',
            items: [{ standard: 'soc2', version: '2026', controlId: 'CC7.2', title: 'Before' }],
          },
        })}
        pendingVersion={createVersion({
          id: 2, version: '1.1.0', status: 'PENDING_REVIEW',
          complianceSnapshot: {
            schemaVersion: '1.0', digest: 'sha256:pending-digest',
            items: [{
              standard: 'soc2', version: '2026', controlId: 'CC7.2', title: 'After',
              evidence: [{ type: 'external-url', url: 'https://example.test/very/long/path', sha256: 'a'.repeat(64) }],
            }],
          },
        })}
      />,
    )

    expect(html).toContain('review.complianceDiffClaimNotice')
    expect(html).toContain('review.complianceDiffBaseDigest')
    expect(html).toContain('review.complianceDiffPendingDigest')
    expect(html).toContain('https://example.test/very/long/path')
    expect(html).toContain('break-all')
    expect(html).toContain('<details')
  })
})

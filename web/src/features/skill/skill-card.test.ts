import { createElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import * as mod from './skill-card'
import { SkillCard } from './skill-card'

vi.mock('@/features/auth/use-auth', () => ({
  useAuth: () => ({ isAuthenticated: false }),
}))

vi.mock('@/features/social/use-star', () => ({
  useStar: () => ({ data: undefined }),
}))

vi.mock('@/shared/ui/card', () => ({
  Card: ({ children, className }: { children?: ReactNode; className?: string }) => (
    createElement('div', { className }, children)
  ),
}))

vi.mock('@/shared/components/namespace-badge', () => ({
  NamespaceBadge: ({ name }: { name: string }) => createElement('span', null, name),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

/**
 * skill-card.tsx exports a single React component (SkillCard).
 * All visual logic is in JSX and depends on hooks (useAuth, useStar).
 * There are no exported pure helpers or constants to test here.
 *
 * We verify the module shape so downstream consumers break fast
 * if the export contract changes.
 */
describe('skill-card module exports', () => {
  it('exports the SkillCard component', () => {
    expect(mod.SkillCard).toBeDefined()
    expect(typeof mod.SkillCard).toBe('function')
  })

  it('renders at most two publisher-declaration badges and an overflow count', () => {
    const html = renderToStaticMarkup(
      createElement(SkillCard, {
        skill: {
          id: 1,
          slug: 'audit-runner',
          displayName: 'Audit Runner',
          downloadCount: 10,
          starCount: 2,
          ratingCount: 0,
          namespace: 'global',
          updatedAt: '2026-08-07T00:00:00Z',
          canSubmitPromotion: false,
          complianceSnapshot: {
            schemaVersion: '1.0',
            digest: 'sha256:demo',
            items: [
              { standard: 'mitre-attack', controlId: 'T1059' },
              { standard: 'nist-csf', controlId: 'PR.AA-01' },
              { standard: 'soc2', controlId: 'CC6.1' },
            ],
          },
        },
      }),
    )

    expect(html).toContain('mitre-attack')
    expect(html).toContain('nist-csf')
    expect(html).not.toContain('soc2')
    expect(html).toContain('+1')
    expect(html).toContain('data-compliance-claim-badge')
    expect(html).toContain('aria-label="compliance.badgeLabel"')
  })

  it('does not render declaration badges without a usable snapshot', () => {
    const html = renderToStaticMarkup(
      createElement(SkillCard, {
        skill: {
          id: 1,
          slug: 'plain-skill',
          displayName: 'Plain Skill',
          downloadCount: 0,
          starCount: 0,
          ratingCount: 0,
          namespace: 'global',
          updatedAt: '2026-08-07T00:00:00Z',
          canSubmitPromotion: false,
          complianceSnapshot: { schemaVersion: '1.0', digest: 'sha256:empty', items: [] },
        },
      }),
    )

    expect(html).not.toContain('data-compliance-claim-badge')
  })
})

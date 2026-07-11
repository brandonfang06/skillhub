import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'


vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ namespace: 'global', slug: 'notes' }),
  useSearch: () => ({ version: '1.0.0' }),
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/shared/hooks/use-skill-queries', () => ({
  useSkillDetail: () => ({
    data: {
      displayName: 'Notes',
      publishedVersion: { version: '1.0.0' },
    },
  }),
  useSkillVersions: () => ({ data: [{ version: '1.0.0' }] }),
}))

vi.mock('@/features/playground/use-playground', () => ({
  usePlayground: () => ({
    state: 'ready',
    messages: [],
    session: {
      sessionId: 'session-1',
      modelKey: 'primary',
      skill: {
        namespace: 'global',
        slug: 'notes',
        displayName: 'Notes',
        version: '1.0.0',
      },
      contextFiles: [{ path: 'SKILL.md', content: 'Instructions' }],
    },
    send: vi.fn(),
    reset: vi.fn(),
    isSending: false,
  }),
}))

import { SkillPlaygroundPage } from './skill-playground'


describe('SkillPlaygroundPage', () => {
  it('renders a scoped dark workspace with a route back to the skill', () => {
    const html = renderToStaticMarkup(<SkillPlaygroundPage />)

    expect(html).toContain('playground.backToSkill')
    expect(html).toContain('data-playground-workspace="true"')
    expect(html).toContain('bg-[#09090B]')
    expect(html).toContain('h-[calc(100dvh-13rem)]')
    expect(html).toContain(
      'min-[900px]:h-[clamp(28rem,calc(100dvh-13rem),48rem)]',
    )
    expect(html).toContain('data-playground-mobile-limits="true"')
    expect(html).toContain('playground.openContext')
  })

  it('keeps chat before read-only context in document order', () => {
    const html = renderToStaticMarkup(<SkillPlaygroundPage />)

    expect(html.indexOf('data-playground-chat')).toBeGreaterThan(-1)
    expect(html.indexOf('data-playground-context-panel')).toBeGreaterThan(-1)
    expect(html.indexOf('data-playground-chat')).toBeLessThan(
      html.indexOf('data-playground-context-panel'),
    )
  })
})

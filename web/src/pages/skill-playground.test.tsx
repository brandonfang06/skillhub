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
    state: 'unavailable',
    messages: [],
    session: null,
    send: vi.fn(),
    reset: vi.fn(),
    isSending: false,
  }),
}))

import { SkillPlaygroundPage } from './skill-playground'


describe('SkillPlaygroundPage', () => {
  it('shows a local unavailable state with a route back to the skill', () => {
    const html = renderToStaticMarkup(<SkillPlaygroundPage />)

    expect(html).toContain('playground.unavailableTitle')
    expect(html).toContain('playground.backToSkill')
  })
})

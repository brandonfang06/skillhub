import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { ReviewProgressPage } from './review-progress'

vi.mock('@/features/review/namespace-reviewers-card', () => ({
  NamespaceReviewersCard: ({ skillId, version }: { skillId: number; version: string }) => <div data-skill-id={skillId} data-version={version} />,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'zh-TW' } }),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useSearch: () => ({}),
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
}))

vi.mock('@/features/review/use-my-review-progress', () => ({
  useMyReviewProgress: () => ({
    data: {
      items: [{
        latestReviewTaskId: 42,
        skillId: 7,
        namespace: 'team-a',
        skillSlug: 'demo-skill',
        skillVersion: '1.2.0',
        latestStatus: 'REJECTED',
        latestReviewComment: 'Please add tests.',
        latestSubmittedAt: '2026-09-01T01:00:00Z',
        latestReviewedAt: '2026-09-01T02:00:00Z',
        attemptCount: 2,
      }],
      total: 1,
      page: 0,
      size: 20,
      statusCounts: { pending: 0, approved: 0, rejected: 1 },
    },
    isLoading: false,
    isError: false,
  }),
  useMyReviewAttempts: () => ({ data: [], isLoading: false, isError: false }),
}))

describe('ReviewProgressPage', () => {
  it('shows the author result and a safe resubmission route', () => {
    const html = renderToStaticMarkup(<ReviewProgressPage />)

    expect(html).toContain('@team-a/demo-skill')
    expect(html).toContain('reviewProgress.statusRejected')
    expect(html).toContain('reviewProgress.resubmit')
    expect(html).toContain('/dashboard/publish')
    expect(html).not.toContain('reviews.typeSkill')
  })
})

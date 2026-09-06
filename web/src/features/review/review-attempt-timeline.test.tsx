import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { ReviewTask } from '@/api/types'
import { ReviewAttemptTimeline } from './review-attempt-timeline'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) => (
      values ? `${key}:${Object.values(values).join(':')}` : key
    ),
  }),
}))

describe('ReviewAttemptTimeline', () => {
  it('renders retained attempts whose original version row has been deleted', () => {
    const attempts: ReviewTask[] = [{
      id: 1,
      skillVersionId: null,
      namespace: 'team-a',
      skillSlug: 'demo',
      version: '1.0.0',
      status: 'REJECTED',
      superseded: true,
      artifactAvailable: false,
      submittedBy: 'author',
      reviewedBy: 'reviewer',
      reviewedByName: 'Reviewer One',
      reviewComment: 'Add tests',
      submittedAt: '2026-09-01T00:00:00Z',
      reviewedAt: '2026-09-01T01:00:00Z',
    }]

    const html = renderToStaticMarkup(<ReviewAttemptTimeline attempts={attempts} locale="en" />)

    expect(html).toContain('reviewProgress.attemptNumber:1')
    expect(html).toContain('reviewProgress.reviewedBy:Reviewer One')
    expect(html).toContain('Add tests')
  })
})

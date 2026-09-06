/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ save: vi.fn(), clear: vi.fn(), moderate: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ i18n: { language: 'en' }, t: (key: string) => key }) }))
vi.mock('@/features/auth/use-auth', () => ({ useAuth: () => ({ isAuthenticated: true, hasRole: (role: string) => role === 'SKILL_ADMIN' }) }))
vi.mock('@/shared/lib/date-time', () => ({ formatLocalDateTime: (value: string) => value }))
vi.mock('@/shared/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('./use-skill-reviews', () => ({
  useSkillReviews: () => ({ data: { items: [{ id: 8, displayName: 'Alice', score: 5, reviewText: 'Great', status: 'VISIBLE', authoredByViewer: false, createdAt: '2026-09-01T00:00:00Z', updatedAt: '2026-09-01T00:00:00Z', lockVersion: 0 }], total: 1, page: 0, size: 20 }, isLoading: false, isError: false }),
  useMySkillReview: () => ({ data: { rated: true, score: 4, reviewed: true, reviewId: 7, reviewText: 'Useful', status: 'HIDDEN', moderationReason: 'Secrets', updatedAt: '2026-09-01T00:00:00Z', lockVersion: 3 } }),
  useUpsertSkillReview: () => ({ mutate: mocks.save, isPending: false }),
  useClearSkillReview: () => ({ mutate: mocks.clear, isPending: false }),
  useModerateSkillReview: () => ({ mutate: mocks.moderate, isPending: false }),
}))

import { SkillReviews } from './skill-reviews'

describe('SkillReviews', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('shows hidden state, supports author editing, and exposes moderation', () => {
    render(<SkillReviews skillId={10} canInteract onRequireLogin={vi.fn()} />)
    expect(screen.getByText(/skillReviews\.yourReviewHidden/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'skillReviews.edit' }))
    expect(screen.getByRole('textbox', { name: 'skillReviews.reviewTextLabel' })).toHaveProperty('value', 'Useful')
    fireEvent.click(screen.getByRole('button', { name: 'skillReviews.hide' }))
    expect(mocks.moderate).toHaveBeenCalled()
  })
})

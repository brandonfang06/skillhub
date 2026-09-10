import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { NamespaceReviewContextContent, NamespaceReviewersCard } from './namespace-reviewers-card'
import type { VersionReviewContext } from './use-review-context'
import en from '@/i18n/locales/en.json'
import zh from '@/i18n/locales/zh.json'
import tw from '@/i18n/locales/zh-TW.json'
import ru from '@/i18n/locales/ru.json'

const mocks = vi.hoisted(() => ({ query: vi.fn(), auth: vi.fn() }))
vi.mock('./use-review-context', () => ({ useReviewContext: mocks.query }))
vi.mock('@/features/auth/use-auth', () => ({ useAuth: mocks.auth }))

vi.mock('react-i18next', async (importOriginal) => ({ ...await importOriginal<typeof import('react-i18next')>(), useTranslation: () => ({
  t: (key: string, args?: Record<string, unknown>) => `${key}${args ? JSON.stringify(args) : ''}`,
  i18n: { language: 'en' },
}) }))

const context: VersionReviewContext = {
  skillId: 1, version: '2.0.0', namespace: 'team', namespaceType: 'TEAM',
  versionStatus: 'PENDING_REVIEW', reviewTaskId: 2, reviewStatus: 'PENDING',
  waitingReason: 'HUMAN_REVIEW', submittedAt: '2026-09-10T00:00:00Z',
  reviewedAt: null, reviewedByName: null, reviewComment: null,
  reviewers: [{ userId: 'internal-id', displayName: 'Alice', loginName: 'alice.login' }],
  total: 1, page: 0, size: 5,
}

function render(data: VersionReviewContext) {
  return renderToStaticMarkup(<NamespaceReviewContextContent data={data} onPageChange={() => {}} />)
}

describe('Namespace reviewers', () => {
  it('keeps loading, forbidden/error, and empty membership distinct', () => {
    mocks.auth.mockReturnValue({ user: { userId: 'publisher' } })
    mocks.query.mockReturnValue({ isPending: true })
    expect(renderToStaticMarkup(<NamespaceReviewersCard skillId={1} version="1.0.0" />)).toContain('namespaceReviewers.loading')
    mocks.query.mockReturnValue({ isPending: false, isError: true, refetch: vi.fn() })
    const html = renderToStaticMarkup(<NamespaceReviewersCard skillId={1} version="1.0.0" />)
    expect(html).toContain('namespaceReviewers.error')
    expect(html).toContain('namespaceReviewers.retry')
    expect(html).not.toContain('namespaceReviewers.empty')
  })
  it('hides the card after logout and lazily enables collapsed progress rows', () => {
    mocks.auth.mockReturnValue({ user: null })
    expect(renderToStaticMarkup(<NamespaceReviewersCard skillId={1} version="1.0.0" />)).toBe('')
    mocks.auth.mockReturnValue({ user: { userId: 'publisher' } })
    const html = renderToStaticMarkup(<NamespaceReviewersCard skillId={1} version="1.0.0" defaultExpanded={false} />)
    expect(mocks.query).toHaveBeenLastCalledWith(1, '1.0.0', 'publisher', 0, false)
    expect(html).toContain('aria-expanded="false"')
    expect(html).not.toContain('namespaceReviewers.error')
  })
  it('shows names and login, never raw IDs or assigned-reviewer claims', () => {
    const html = render(context)
    expect(html).toContain('Alice')
    expect(html).toContain('alice.login')
    expect(html).not.toContain('internal-id')
    expect(html).toContain('namespaceReviewers.anyOne')
  })
  it('distinguishes scan blocking from waiting for a person', () => {
    const html = render({ ...context, waitingReason: 'SCAN_PARTIAL' })
    expect(html).toContain('namespaceReviewers.reasons.SCAN_PARTIAL')
    expect(html).not.toContain('namespaceReviewers.anyOne')
  })
  it('keeps completed reviewer evidence instead of current membership', () => {
    const html = render({ ...context, waitingReason: 'APPROVED', reviewedByName: 'Former Admin', reviewComment: '<script>bad</script>' })
    expect(html).toContain('Former Admin')
    expect(html).not.toContain('Alice')
    expect(html).toContain('&lt;script&gt;')
  })
  it('gives GLOBAL its platform flow without enumerating people', () => {
    const html = render({ ...context, namespaceType: 'GLOBAL' })
    expect(html).toContain('namespaceReviewers.global')
    expect(html).not.toContain('Alice')
  })
  it('does not mistake an uploaded draft for pending review', () => {
    const html = render({ ...context, waitingReason: 'NOT_SUBMITTED' })
    expect(html).toContain('namespaceReviewers.reasons.NOT_SUBMITTED')
    expect(html).not.toContain('Alice')
  })
  it('supports empty membership and complete paginated lists', () => {
    expect(render({ ...context, reviewers: [], total: 0 })).toContain('namespaceReviewers.empty')
    expect(render({ ...context, total: 8 })).toContain('namespaceReviewers.next')
  })
  it('supplies matching translations in every supported locale', () => {
    for (const locale of [en, zh, tw, ru]) {
      expect(Object.keys(locale.namespaceReviewers).sort()).toEqual(Object.keys(en.namespaceReviewers).sort())
      expect(Object.keys(locale.namespaceReviewers.reasons).sort()).toEqual(Object.keys(en.namespaceReviewers.reasons).sort())
    }
    expect(tw.namespaceReviewers.title).toBe('Namespace 可審核人員')
  })
})

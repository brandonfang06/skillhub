import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SecurityAuditRecord } from '@/features/security-audit/types'

const navigateMock = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  useParams: (options?: { from?: string }) => (
    options?.from === '/dashboard/namespaces/$slug/reviews/$id'
      ? { id: '13', slug: 'team-alpha' }
      : { id: '13' }
  ),
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, string>) =>
        values?.skill ? `${key}:${values.skill}` : key,
      i18n: { language: 'zh' },
    }),
  }
})

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: undefined, isLoading: false, error: null }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/shared/lib/date-time', () => ({
  formatLocalDateTime: (value: string) => value,
}))

vi.mock('@/shared/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/features/review/review-error', () => ({
  resolveReviewActionErrorDescription: () => 'error',
}))

const useReviewDetailMock = vi.fn<() => unknown>(() => ({
  data: {
    id: 13,
    namespace: 'global',
    skillSlug: 'demo-skill',
    version: '1.2.0',
    status: 'PENDING',
    submittedBy: 'local-admin',
    submittedByName: 'Local Admin',
    submittedAt: '2026-03-19T00:00:00Z',
    reviewedBy: null,
    reviewedByName: null,
    reviewedAt: null,
    reviewComment: null,
  },
  isLoading: false,
}))

const useReviewSkillDetailMock = vi.fn<(...args: [number, boolean?]) => unknown>(() => ({
  data: {
    skill: {
      id: 1,
      slug: 'demo-skill',
      displayName: 'Demo Skill',
      visibility: 'PUBLIC',
      status: 'ACTIVE',
      downloadCount: 3,
      starCount: 1,
      ratingCount: 0,
      hidden: false,
      namespace: 'global',
      canManageLifecycle: false,
      canSubmitPromotion: false,
      canInteract: false,
      canReport: false,
      resolutionMode: 'REVIEW_TASK',
    },
    versions: [
      {
        id: 10,
        version: '1.2.0',
        status: 'PENDING_REVIEW',
        changelog: 'Pending update',
        fileCount: 2,
        totalSize: 120,
        publishedAt: '2026-03-19T00:00:00Z',
        downloadAvailable: true,
      },
    ],
    files: [],
    documentationPath: 'README.md',
    documentationContent: '# Demo Skill',
    downloadUrl: '/api/v1/reviews/13/download',
    activeVersion: '1.2.0',
  },
  isLoading: false,
  error: null,
}))

vi.mock('@/features/review/use-review-detail', () => ({
  useReviewDetail: () => useReviewDetailMock(),
  useReviewSkillDetail: (taskId: number, enabled?: boolean) => useReviewSkillDetailMock(taskId, enabled),
  useApproveReview: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useRejectReview: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}))

let securityAuditsMock: SecurityAuditRecord[] = []
let securityAuditsLoading = false
let securityAuditsError: Error | null = null

function createPartialAudit(): SecurityAuditRecord {
  return {
    id: 21,
    scanId: 'scan-partial',
    scannerType: 'skill-scanner',
    verdict: 'SAFE',
    isSafe: true,
    maxSeverity: null,
    findingsCount: 0,
    findings: [],
    scanDurationSeconds: 3,
    scannedAt: '2026-03-19T00:01:00Z',
    createdAt: '2026-03-19T00:00:00Z',
    scanStatus: 'PARTIAL',
    analyzersCompleted: ['static_analyzer'],
    analyzerFailures: [{ analyzer: 'llm_analyzer', code: 'LLM_TIMEOUT' }],
    failureCode: 'LLM_TIMEOUT',
  }
}

vi.mock('@/features/security-audit/use-security-audit', () => ({
  useSecurityAudits: () => ({
    data: securityAuditsMock,
    isLoading: securityAuditsLoading,
    error: securityAuditsError,
  }),
}))

const userMock = { platformRoles: ['SKILL_ADMIN'] as string[] }
vi.mock('@/features/auth/use-auth', () => ({
  useAuth: () => ({ user: userMock }),
}))

// Mock hooks used directly by the review-detail page for file browser sidebar
vi.mock('@/features/review/use-review-file', () => ({
  useReviewFile: () => ({ data: null, isLoading: false, error: null }),
}))

vi.mock('@/api/client', () => ({
  buildApiUrl: (path: string) => path,
  WEB_API_PREFIX: '/api/web',
}))

import { NamespaceReviewDetailPage, ReviewDetailPage } from './review-detail'

describe('ReviewDetailPage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    userMock.platformRoles = ['SKILL_ADMIN']
    securityAuditsMock = []
    securityAuditsLoading = false
    securityAuditsError = null
    useReviewDetailMock.mockReset()
    useReviewSkillDetailMock.mockReset()
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'global',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedByName: 'Local Admin',
        submittedAt: '2026-03-19T00:00:00Z',
        reviewedBy: null,
        reviewedByName: null,
        reviewedAt: null,
        reviewComment: null,
      },
      isLoading: false,
    })
    useReviewSkillDetailMock.mockReturnValue({
      data: {
        skill: {
          id: 1,
          slug: 'demo-skill',
          displayName: 'Demo Skill',
          visibility: 'PUBLIC',
          status: 'ACTIVE',
          downloadCount: 3,
          starCount: 1,
          ratingCount: 0,
          hidden: false,
          namespace: 'global',
          canManageLifecycle: false,
          canSubmitPromotion: false,
          canInteract: false,
          canReport: false,
          resolutionMode: 'REVIEW_TASK',
        },
        versions: [
          {
            id: 10,
            version: '1.2.0',
            status: 'PENDING_REVIEW',
            changelog: 'Pending update',
            fileCount: 2,
            totalSize: 120,
            publishedAt: '2026-03-19T00:00:00Z',
            downloadAvailable: true,
          },
        ],
        files: [],
        documentationPath: 'README.md',
        documentationContent: '# Demo Skill',
        downloadUrl: '/api/v1/reviews/13/download',
        activeVersion: '1.2.0',
      },
      isLoading: false,
      error: null,
    })
  })

  it('keeps the page in a single-column flow and leaves the skill detail behind a collapsed section', () => {
    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('max-w-6xl mx-auto flex')
    expect(html).toContain('aria-expanded="false"')
  })

  it('renders not-found state when the review record is missing', () => {
    useReviewDetailMock.mockReturnValue({
      data: null,
      isLoading: false,
    })

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('review.notFound')
  })

  it('renders namespace review detail through the namespace route wrapper', () => {
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'team-alpha',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedByName: 'Local Admin',
        submittedAt: '2026-03-19T00:00:00Z',
        reviewedBy: null,
        reviewedByName: null,
        reviewedAt: null,
        reviewComment: null,
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespaceReviewDetailPage />)

    expect(html).toContain('review.detail')
    expect(html).toContain('demo-skill')
  })

  it('shows the visibility requested by the version under namespace review', () => {
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'team-alpha',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        requestedVisibility: 'NAMESPACE_ONLY',
        approvalVisibility: 'NAMESPACE_ONLY',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedByName: 'Local Admin',
        submittedAt: '2026-03-19T00:00:00Z',
        reviewedBy: null,
        reviewedByName: null,
        reviewedAt: null,
        reviewComment: null,
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespaceReviewDetailPage />)

    expect(html).toContain('review.requestedVisibility')
    expect(html).toContain('publish.visibilityOptions.namespaceOnly')
    expect(html).not.toContain('review.approvalVisibility')
  })

  it('warns when approval will use a newer visibility than the submitted value', () => {
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'team-alpha',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        requestedVisibility: 'NAMESPACE_ONLY',
        approvalVisibility: 'PRIVATE',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedAt: '2026-03-19T00:00:00Z',
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespaceReviewDetailPage />)

    expect(html).toContain('review.requestedVisibility')
    expect(html).toContain('publish.visibilityOptions.namespaceOnly')
    expect(html).toContain('review.approvalVisibility')
    expect(html).toContain('publish.visibilityOptions.private')
    expect(html).toContain('review.visibilityChangedAfterSubmission')
  })

  it('shows a neutral fallback when requested visibility was not recorded', () => {
    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('review.requestedVisibility')
    expect(html).toContain('review.visibilityNotRecorded')
  })

  it('shows a known approval visibility when a legacy request was not recorded', () => {
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'team-alpha',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        requestedVisibility: null,
        approvalVisibility: 'PRIVATE',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedAt: '2026-03-19T00:00:00Z',
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespaceReviewDetailPage />)

    expect(html).toContain('review.visibilityNotRecorded')
    expect(html).toContain('review.approvalVisibility')
    expect(html).toContain('publish.visibilityOptions.private')
    expect(html).toContain('review.visibilityChangedAfterSubmission')
  })

  it('shows public when public visibility was requested', () => {
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'global',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        requestedVisibility: 'PUBLIC',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedAt: '2026-03-19T00:00:00Z',
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('publish.visibilityOptions.public')
  })

  it('uses the logged-in users label for global namespace-only reviews', () => {
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'global',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        requestedVisibility: 'NAMESPACE_ONLY',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedAt: '2026-03-19T00:00:00Z',
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('publish.visibilityOptions.loggedInUsersOnly')
  })

  it('redirects namespace reviews opened through the global route for namespace operators', () => {
    userMock.platformRoles = []
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'team-alpha',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedByName: 'Local Admin',
        submittedAt: '2026-03-19T00:00:00Z',
        reviewedBy: null,
        reviewedByName: null,
        reviewedAt: null,
        reviewComment: null,
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toBe('')
  })

  it('shows not-found state when the namespace route slug does not match the review namespace', () => {
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'other-team',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedByName: 'Local Admin',
        submittedAt: '2026-03-19T00:00:00Z',
        reviewedBy: null,
        reviewedByName: null,
        reviewedAt: null,
        reviewComment: null,
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespaceReviewDetailPage />)

    expect(html).toContain('review.notFound')
    expect(html).toContain('review.backToList')
  })

  it('disables approval and shows a scanning hint while the active review version is scanning', () => {
    useReviewSkillDetailMock.mockReturnValue({
      data: {
        skill: {
          id: 1,
          slug: 'demo-skill',
          displayName: 'Demo Skill',
          visibility: 'PUBLIC',
          status: 'ACTIVE',
          downloadCount: 3,
          starCount: 1,
          ratingCount: 0,
          hidden: false,
          namespace: 'global',
          canManageLifecycle: false,
          canSubmitPromotion: false,
          canInteract: false,
          canReport: false,
          resolutionMode: 'REVIEW_TASK',
        },
        versions: [
          {
            id: 10,
            version: '1.2.0',
            status: 'SCANNING',
            changelog: 'Pending update',
            fileCount: 2,
            totalSize: 120,
            publishedAt: '2026-03-19T00:00:00Z',
            downloadAvailable: true,
          },
        ],
        files: [],
        documentationPath: 'README.md',
        documentationContent: '# Demo Skill',
        downloadUrl: '/api/v1/reviews/13/download',
        activeVersion: '1.2.0',
      },
      isLoading: false,
      error: null,
    })

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('review.approveDisabledScanning')
    expect(html).toContain('disabled=""')
  })

  it('blocks approval when the active review version scan failed', () => {
    useReviewSkillDetailMock.mockReturnValue({
      data: {
        skill: { id: 1 },
        versions: [{ id: 10, version: '1.2.0', status: 'SCAN_FAILED' }],
        files: [],
        downloadUrl: '/api/v1/reviews/13/download',
        activeVersion: '1.2.0',
      },
      isLoading: false,
      error: null,
    })

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('review.approveDisabledScanFailed')
    expect(html).toMatch(/data-review-approve="true"[^>]*disabled=""/)
  })

  it('blocks approval until security scan evidence finishes loading', () => {
    securityAuditsLoading = true

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('review.approveDisabledAuditLoading')
    expect(html).toMatch(/data-review-approve="true"[^>]*disabled=""/)
  })

  it('blocks approval when security scan evidence cannot be loaded', () => {
    securityAuditsError = new Error('audit unavailable')

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('review.approveDisabledAuditUnavailable')
    expect(html).toMatch(/data-review-approve="true"[^>]*disabled=""/)
  })

  it('requires the dedicated override flow for platform administrators when the LLM scan is partial', () => {
    securityAuditsMock = [createPartialAudit()]

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(html).toContain('review.scanOverrideRequired')
    expect(html).not.toMatch(/data-review-approve="true"[^>]*disabled=""/)
  })

  it('blocks namespace reviewers from overriding a partial LLM scan', () => {
    userMock.platformRoles = []
    securityAuditsMock = [createPartialAudit()]
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        namespace: 'team-alpha',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        status: 'PENDING',
        submittedBy: 'local-admin',
        submittedAt: '2026-03-19T00:00:00Z',
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<NamespaceReviewDetailPage />)

    expect(html).toContain('review.approveDisabledPartialNamespace')
    expect(html).toMatch(/data-review-approve="true"[^>]*disabled=""/)
  })

  it('renders archived feedback without requesting or exposing artifact actions', () => {
    useReviewDetailMock.mockReturnValue({
      data: {
        id: 13,
        skillVersionId: 9,
        namespace: 'global',
        skillSlug: 'demo-skill',
        version: '1.2.0',
        status: 'REJECTED',
        submittedBy: 'local-admin',
        submittedByName: 'Local Admin',
        submittedAt: '2026-03-19T00:00:00Z',
        reviewedBy: 'reviewer',
        reviewedByName: 'Reviewer',
        reviewedAt: '2026-03-19T01:00:00Z',
        reviewComment: 'Fix the manifest',
        superseded: true,
        artifactAvailable: false,
        replacementVersionId: 10,
        replacementReviewTaskId: 14,
        archivedSnapshot: {
          metadata: { name: 'Demo Skill' },
          manifest: [{ path: 'SKILL.md', size: 12 }],
          files: [
            {
              path: 'SKILL.md',
              size: 12,
              contentType: 'text/markdown',
              sha256: 'archived-sha',
            },
          ],
          scannerSummary: [],
        },
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<ReviewDetailPage />)

    expect(useReviewSkillDetailMock).toHaveBeenCalledWith(13, false)
    expect(html).toContain('data-archived-review')
    expect(html).toContain('review.supersededTitle')
    expect(html).toContain('Fix the manifest')
    expect(html).toContain('archived-sha')
    expect(html).toContain('review.openReplacementReview')
    expect(html).not.toContain('review.downloadSkillZip')
    expect(html).not.toContain('review.skillDetailTitle')
  })
})

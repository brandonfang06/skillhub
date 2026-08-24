// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigateMock = vi.fn()
const useSearchMock = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  useSearch: () => useSearchMock(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

const useAggregateMock = vi.fn()
const useSkillsMock = vi.fn()
vi.mock('./use-namespace-security-analytics', () => ({
  useNamespaceSecurityAnalytics: (params: unknown) => useAggregateMock(params),
  useNamespaceSecuritySkills: (namespaceId: number | undefined, params: unknown) => (
    useSkillsMock(namespaceId, params)
  ),
}))

vi.mock('@/features/security-audit/security-audit-section', () => ({
  SecurityAuditSection: ({ skillId, versionId }: { skillId: number; versionId: number }) => (
    <div data-testid="security-audit-detail">{skillId}:{versionId}</div>
  ),
}))

vi.mock('@/shared/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => null,
}))

import { NamespaceSecurityAnalyticsView } from './namespace-security-analytics-view'

const securitySearch = {
  view: 'security',
  namespaceType: 'ALL',
  namespaceStatus: 'ALL',
  period: '30d',
  sort: 'periodDownloads',
  direction: 'desc',
  page: 0,
  size: 20,
  severity: 'ALL',
  skillStatus: 'ALL',
  visibility: 'ALL',
  hidden: 'ALL',
  versionStatus: 'ALL',
  securitySort: 'risk',
  securityDirection: 'desc',
  securityPage: 0,
  securitySize: 20,
}

const severityCounts = {
  critical: 2,
  high: 3,
  medium: 4,
  low: 5,
  info: 6,
  unclassified: 1,
}

const aggregateData = {
  summary: {
    affectedNamespaceCount: 2,
    affectedSkillCount: 3,
    affectedVersionCount: 8,
    findingCount: 21,
    severityCounts,
  },
  items: [{
    namespaceId: 42,
    slug: 'private-lab',
    displayName: 'Private Lab',
    type: 'TEAM',
    status: 'ARCHIVED',
    affectedSkillCount: 1,
    affectedVersionCount: 2,
    findingCount: 5,
    maxSeverity: 'CRITICAL',
    severityCounts,
    latestScanAt: '2026-08-24T04:00:00Z',
  }],
  page: 0,
  size: 20,
  total: 1,
}

const skillsData = {
  items: [{
    skillId: 91,
    slug: 'draft-agent',
    displayName: 'Draft Agent',
    ownerId: 'oauth-subject',
    ownerDisplayName: 'Alice',
    status: 'ARCHIVED',
    visibility: 'PRIVATE',
    hidden: true,
    affectedVersionCount: 2,
    findingCount: 5,
    maxSeverity: 'CRITICAL',
    severityCounts,
    latestScanAt: '2026-08-24T04:00:00Z',
    versions: [{
      versionId: 901,
      version: '2026.08.24',
      status: 'UPLOADED',
      scannerTypes: ['skill-scanner'],
      findingCount: 5,
      maxSeverity: 'CRITICAL',
      severityCounts,
      latestScanAt: '2026-08-24T04:00:00Z',
    }],
  }],
  page: 0,
  size: 20,
  total: 1,
}

describe('NamespaceSecurityAnalyticsView', () => {
  afterEach(cleanup)

  beforeEach(() => {
    navigateMock.mockReset()
    useSearchMock.mockReturnValue(securitySearch)
    useAggregateMock.mockReturnValue({
      data: aggregateData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
    useSkillsMock.mockImplementation((namespaceId: number | undefined) => ({
      data: namespaceId === 42 ? skillsData : undefined,
      isLoading: false,
      isError: false,
    }))
  })

  it('shows cross-lifecycle risk, lazily expands skills, and loads details only after selection', () => {
    render(<NamespaceSecurityAnalyticsView />)

    expect(screen.getByText('namespaceSecurity.summaryNamespaces')).toBeTruthy()
    expect(screen.getByText('Private Lab')).toBeTruthy()
    expect(screen.getByText('@private-lab')).toBeTruthy()
    expect(screen.queryByTestId('security-audit-detail')).toBeNull()
    expect(useSkillsMock).toHaveBeenLastCalledWith(undefined, expect.anything())

    fireEvent.click(screen.getByRole('button', { name: 'namespaceSecurity.expandNamespace' }))

    expect(useSkillsMock).toHaveBeenLastCalledWith(42, expect.anything())
    expect(screen.getByText('Draft Agent')).toBeTruthy()
    expect(screen.getByText('Alice')).toBeTruthy()
    expect(screen.getAllByText('PRIVATE').length).toBeGreaterThan(0)
    expect(screen.getAllByText('UPLOADED').length).toBeGreaterThan(0)
    expect(screen.queryByTestId('security-audit-detail')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '2026.08.24' }))

    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByTestId('security-audit-detail').textContent).toBe('91:901')
  })

  it('turns a severity summary into a URL-backed filter', () => {
    render(<NamespaceSecurityAnalyticsView />)

    fireEvent.click(screen.getByRole('button', { name: 'namespaceSecurity.severityCritical' }))

    expect(navigateMock).toHaveBeenCalledWith({
      search: expect.objectContaining({
        ...securitySearch,
        severity: 'CRITICAL',
        securityPage: 0,
      }),
    })
  })

  it('paginates the lazy skill list without changing aggregate URL filters', () => {
    useSkillsMock.mockImplementation((namespaceId: number | undefined) => ({
      data: namespaceId === 42 ? { ...skillsData, total: 25 } : undefined,
      isLoading: false,
      isError: false,
    }))
    render(<NamespaceSecurityAnalyticsView />)

    fireEvent.click(screen.getByRole('button', { name: 'namespaceSecurity.expandNamespace' }))
    fireEvent.click(screen.getByRole('button', { name: 'namespaceSecurity.nextSkillsPage' }))

    expect(useSkillsMock).toHaveBeenLastCalledWith(42, expect.objectContaining({ page: 1, size: 20 }))
    expect(navigateMock).not.toHaveBeenCalled()
  })
})

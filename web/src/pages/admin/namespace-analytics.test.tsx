// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigateMock = vi.fn()
const useSearchMock = vi.fn()
const { translateMock } = vi.hoisted(() => ({
  translateMock: vi.fn((key: string) => key),
}))
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  useSearch: () => useSearchMock(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: translateMock,
    i18n: { language: 'en' },
  }),
}))

vi.mock('@/shared/ui/card', () => ({
  Card: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))

vi.mock('@/shared/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))

vi.mock('@/shared/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => null,
  normalizeSelectValue: (value: string) => value,
}))

vi.mock('@/shared/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children }: { children: React.ReactNode }) => <td>{children}</td>,
  TableHead: ({ children }: { children: React.ReactNode }) => <th>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))

vi.mock('@/shared/components/namespace-badge', () => ({
  NamespaceBadge: ({ type, name }: { type: string; name: string }) => <span>{type}:{name}</span>,
}))

const refetchMock = vi.fn()
const useNamespaceAnalyticsMock = vi.fn()
vi.mock('@/features/admin/use-namespace-analytics', () => ({
  useNamespaceAnalytics: (params: unknown) => useNamespaceAnalyticsMock(params),
}))

vi.mock('@/features/admin/namespace-security-analytics-view', () => ({
  NamespaceSecurityAnalyticsView: () => <div data-testid="namespace-security-view" />,
}))

const exportNamespaceAnalyticsCsvMock = vi.fn()
vi.mock('@/features/admin/export-namespace-analytics', () => ({
  exportNamespaceAnalyticsCsv: (params: unknown) => exportNamespaceAnalyticsCsvMock(params),
}))

const toastSuccessMock = vi.fn()
const toastWarningMock = vi.fn()
const toastErrorMock = vi.fn()
vi.mock('@/shared/lib/toast', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    warning: (...args: unknown[]) => toastWarningMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}))

import { NamespaceAnalyticsPage } from './namespace-analytics'

const defaultSearch = {
  view: 'catalog',
  namespaceType: 'ALL',
  namespaceStatus: 'ACTIVE',
  period: '30d',
  sort: 'periodDownloads',
  direction: 'desc',
  page: 0,
  size: 20,
}

const analyticsData = {
  summary: {
    namespaceCount: 2,
    maintainerCount: 3,
    skillCount: 5,
    lifetimeDownloads: 120,
    periodDownloads: 18,
  },
  period: {
    startTime: '2026-07-05T00:00:00Z',
    endTime: '2026-08-04T00:00:00Z',
    source: 'cli',
    retentionMonths: 12,
  },
  items: [
    {
      namespaceId: 1,
      slug: 'global',
      displayName: 'Global',
      type: 'GLOBAL',
      status: 'ACTIVE',
      maintainerCount: 2,
      skillCount: 3,
      lifetimeDownloads: 80,
      periodDownloads: 12,
    },
  ],
  page: 0,
  size: 20,
  total: 2,
}

describe('NamespaceAnalyticsPage', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    navigateMock.mockReset()
    refetchMock.mockReset()
    translateMock.mockClear()
    exportNamespaceAnalyticsCsvMock.mockReset()
    exportNamespaceAnalyticsCsvMock.mockResolvedValue({ truncated: false, rowLimit: 10_000 })
    toastSuccessMock.mockReset()
    toastWarningMock.mockReset()
    toastErrorMock.mockReset()
    useSearchMock.mockReturnValue(defaultSearch)
    useNamespaceAnalyticsMock.mockReturnValue({
      data: analyticsData,
      isLoading: false,
      isError: false,
      refetch: refetchMock,
    })
  })

  it('renders summary cards and readable namespace metrics', () => {
    render(<NamespaceAnalyticsPage />)

    expect(screen.getByRole('heading', { name: 'namespaceAnalytics.title' })).toBeTruthy()
    expect(screen.getByText('namespaceAnalytics.summaryNamespaces')).toBeTruthy()
    expect(screen.getByText('namespaceAnalytics.summaryMaintainers')).toBeTruthy()
    expect(screen.getByText('namespaceAnalytics.summarySkills')).toBeTruthy()
    expect(screen.getByText('namespaceAnalytics.summaryLifetimeDownloads')).toBeTruthy()
    expect(screen.getByText('namespaceAnalytics.summaryPeriodDownloads')).toBeTruthy()
    expect(screen.getByText('namespaceAnalytics.periodRange')).toBeTruthy()
    expect(screen.getByText('GLOBAL:namespaceAnalytics.namespaceTypeGlobal')).toBeTruthy()
    expect(screen.getAllByText('namespaceAnalytics.namespaceStatusActive')).toHaveLength(2)
    expect(screen.getByText('@global')).toBeTruthy()
    expect(screen.getByText('80')).toBeTruthy()
    expect(screen.getByText('12')).toBeTruthy()
  })

  it('switches to the security inventory with risk-first URL defaults', () => {
    render(<NamespaceAnalyticsPage />)

    fireEvent.click(screen.getByRole('button', { name: 'namespaceAnalytics.securityView' }))

    expect(navigateMock).toHaveBeenCalledWith({
      search: {
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
      },
    })
  })

  it('lets users type a multi-word namespace query before committing it', () => {
    render(<NamespaceAnalyticsPage />)

    const input = screen.getByPlaceholderText('namespaceAnalytics.searchPlaceholder') as HTMLInputElement
    fireEvent.change(input, {
      target: { value: 'platform ' },
    })
    expect(input.value).toBe('platform ')
    expect(navigateMock).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: 'platform team' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(navigateMock).toHaveBeenCalledWith({
      search: expect.objectContaining({
        ...defaultSearch,
        query: 'platform team',
        page: 0,
      }),
    })
  })

  it('updates sorting and pagination through router search', () => {
    useNamespaceAnalyticsMock.mockReturnValue({
      data: { ...analyticsData, total: 40 },
      isLoading: false,
      isError: false,
      refetch: refetchMock,
    })
    render(<NamespaceAnalyticsPage />)

    fireEvent.click(screen.getByRole('button', { name: 'namespaceAnalytics.colSkills' }))
    expect(navigateMock).toHaveBeenCalledWith({
      search: expect.objectContaining({ sort: 'skills', direction: 'desc', page: 0 }),
    })

    fireEvent.click(screen.getByRole('button', { name: 'namespaceAnalytics.nextPage' }))
    expect(navigateMock).toHaveBeenCalledWith({
      search: expect.objectContaining({ page: 1 }),
    })
  })

  it('drills into Download Events with the server period and source', () => {
    render(<NamespaceAnalyticsPage />)

    fireEvent.click(screen.getByRole('button', { name: 'namespaceAnalytics.viewEvents' }))

    expect(navigateMock).toHaveBeenCalledWith({
      to: '/admin/download-events',
      search: {
        namespace: 'global',
        startTime: '2026-07-05T00:00:00Z',
        endTime: '2026-08-04T00:00:00Z',
        source: 'cli',
      },
    })
  })

  it('exports every row matching the current filters and sorting', async () => {
    useSearchMock.mockReturnValue({
      ...defaultSearch,
      query: 'platform team',
      namespaceType: 'TEAM',
      namespaceStatus: 'ALL',
      source: 'cli',
      sort: 'skills',
      direction: 'asc',
      page: 3,
      size: 50,
    })
    render(<NamespaceAnalyticsPage />)

    fireEvent.click(screen.getByRole('button', { name: 'namespaceAnalytics.exportCsv' }))

    await waitFor(() => expect(exportNamespaceAnalyticsCsvMock).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'platform team',
        namespaceType: 'TEAM',
        namespaceStatus: 'ALL',
        source: 'cli',
        sort: 'skills',
        direction: 'asc',
        page: 3,
        size: 50,
      }),
    ))
    expect(toastSuccessMock).toHaveBeenCalledWith('namespaceAnalytics.exportSuccess')
    expect(toastWarningMock).not.toHaveBeenCalled()
  })

  it('exports the current query draft when users click export without pressing Enter', async () => {
    render(<NamespaceAnalyticsPage />)
    fireEvent.change(screen.getByPlaceholderText('namespaceAnalytics.searchPlaceholder'), {
      target: { value: 'fresh report filter' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'namespaceAnalytics.exportCsv' }))

    await waitFor(() => expect(exportNamespaceAnalyticsCsvMock).toHaveBeenCalledWith(
      expect.objectContaining({ query: 'fresh report filter' }),
    ))
  })

  it('disables duplicate exports and warns when the result is truncated', async () => {
    let resolveExport: ((value: { truncated: boolean; rowLimit: number }) => void) | undefined
    exportNamespaceAnalyticsCsvMock.mockReturnValue(new Promise((resolve) => {
      resolveExport = resolve
    }))
    render(<NamespaceAnalyticsPage />)

    const button = screen.getByRole('button', { name: 'namespaceAnalytics.exportCsv' })
    fireEvent.click(button)

    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(true))
    fireEvent.click(button)
    expect(exportNamespaceAnalyticsCsvMock).toHaveBeenCalledOnce()

    resolveExport?.({ truncated: true, rowLimit: 10_000 })
    await waitFor(() => expect(toastWarningMock).toHaveBeenCalledWith(
      'namespaceAnalytics.exportTruncatedTitle',
      'namespaceAnalytics.exportTruncatedDescription',
    ))
    expect(translateMock).toHaveBeenCalledWith(
      'namespaceAnalytics.exportTruncatedTitle',
      { limit: 10_000 },
    )
  })

  it('shows an export error without changing filters', async () => {
    exportNamespaceAnalyticsCsvMock.mockRejectedValue(new Error('network unavailable'))
    render(<NamespaceAnalyticsPage />)

    fireEvent.click(screen.getByRole('button', { name: 'namespaceAnalytics.exportCsv' }))

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith(
      'namespaceAnalytics.exportError',
      'network unavailable',
    ))
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('shows the empty state and clears filters through router search', () => {
    useNamespaceAnalyticsMock.mockReturnValue({
      data: { ...analyticsData, summary: { ...analyticsData.summary, namespaceCount: 0 }, items: [], total: 0 },
      isLoading: false,
      isError: false,
      refetch: refetchMock,
    })
    render(<NamespaceAnalyticsPage />)

    expect(screen.getByText('namespaceAnalytics.emptyTitle')).toBeTruthy()
    fireEvent.click(screen.getAllByRole('button', { name: 'namespaceAnalytics.clearFilters' })[1])
    expect(navigateMock).toHaveBeenCalledWith({ search: defaultSearch })
  })

  it('preserves filters and retries after an API error', () => {
    useNamespaceAnalyticsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: refetchMock,
    })
    render(<NamespaceAnalyticsPage />)

    fireEvent.click(screen.getByRole('button', { name: 'namespaceAnalytics.retry' }))
    expect(refetchMock).toHaveBeenCalledOnce()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('renders loading skeletons before data arrives', () => {
    useNamespaceAnalyticsMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: refetchMock,
    })
    render(<NamespaceAnalyticsPage />)

    expect(screen.getByTestId('namespace-analytics-loading')).toBeTruthy()
  })
})

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

import { NamespaceAnalyticsPage } from './namespace-analytics'

const defaultSearch = {
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

import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const useSearchMock = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useSearch: () => useSearchMock(),
}))

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: { language: 'en' },
    }),
  }
})

vi.mock('@/shared/lib/date-time', () => ({
  formatLocalDateTime: (value: string) => value,
  toLocalDateTimeInputValue: (value: string) => value.slice(0, 16),
}))

vi.mock('@/shared/ui/card', () => ({
  Card: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/shared/ui/input', () => ({
  Input: ({ placeholder }: { placeholder?: string }) => <input placeholder={placeholder} />,
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children }: { children: unknown }) => children,
  buttonVariants: () => 'button',
}))

vi.mock('@/shared/ui/select', () => ({
  Select: ({ children }: { children: unknown }) => children,
  SelectContent: ({ children }: { children: unknown }) => children,
  SelectItem: ({ children }: { children: unknown }) => children,
  SelectTrigger: ({ children }: { children: unknown }) => children,
  SelectValue: () => null,
  normalizeSelectValue: (v: string) => v || null,
}))

vi.mock('@/shared/ui/table', () => ({
  Table: ({ children }: { children: unknown }) => children,
  TableBody: ({ children }: { children: unknown }) => children,
  TableCell: ({ children }: { children: unknown }) => children,
  TableHead: ({ children }: { children: unknown }) => children,
  TableHeader: ({ children }: { children: unknown }) => children,
  TableRow: ({ children }: { children: unknown }) => children,
}))

const useDownloadEventsMock = vi.fn()
vi.mock('@/features/admin/use-download-events', () => ({
  useDownloadEvents: (params: unknown) => useDownloadEventsMock(params),
}))

import { DownloadEventsPage } from './download-events'

describe('DownloadEventsPage', () => {
  beforeEach(() => {
    useSearchMock.mockReturnValue({})
  })

  it('renders the page title and empty state', () => {
    useDownloadEventsMock.mockReturnValue({
      data: { items: [], total: 0, page: 0, size: 20 },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<DownloadEventsPage />)

    expect(html).toContain('downloadEvents.title')
    expect(html).toContain('downloadEvents.exportCsv')
    expect(html).toContain('title="downloadEvents.exportCsvLimit"')
    expect(html).toContain('placeholder="downloadEvents.userPlaceholder"')
    expect(html).toContain('downloadEvents.empty')
  })

  it('renders download event rows', () => {
    useDownloadEventsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 1,
            skillId: 7,
            skillVersionId: 42,
            namespace: 'team-a',
            slug: 'demo',
            version: '1.0.0',
            source: 'cli',
            userId: 'user-a',
            username: 'User A',
            requestId: 'req-1',
            ipAddress: '127.0.0.1',
            userAgent: 'skillhub-cli',
            createdAt: '2026-07-09T08:00:00Z',
          },
        ],
        total: 1,
        page: 0,
        size: 20,
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<DownloadEventsPage />)

    expect(html).toContain('team-a/demo')
    expect(html).toContain('user-a')
    expect(html.indexOf('User A')).toBeLessThan(html.indexOf('user-a'))
    expect(html).toContain('font-mono')
    expect(html).toContain('skillhub-cli')
  })

  it('falls back to user ID and then the anonymous label', () => {
    useDownloadEventsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 2,
            skillId: 7,
            skillVersionId: 42,
            namespace: 'team-a',
            slug: 'demo',
            version: '1.0.0',
            source: 'web',
            userId: 'opaque-user-id',
            username: null,
            createdAt: '2026-07-09T08:00:00Z',
          },
          {
            id: 3,
            skillId: 7,
            skillVersionId: 42,
            namespace: 'team-a',
            slug: 'demo',
            version: '1.0.0',
            source: 'web',
            userId: null,
            username: null,
            createdAt: '2026-07-09T08:01:00Z',
          },
        ],
        total: 2,
        page: 0,
        size: 20,
      },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<DownloadEventsPage />)

    expect(html).toContain('opaque-user-id')
    expect(html).toContain('downloadEvents.anonymousUser')
  })

  it('initializes drill-down filters from route search parameters', () => {
    useSearchMock.mockReturnValue({
      namespace: 'platform-tools',
      userQuery: 'Brandon',
      source: 'cli',
      startTime: '2026-07-05T00:00:00Z',
      endTime: '2026-08-04T00:00:00Z',
    })
    useDownloadEventsMock.mockReturnValue({
      data: { items: [], total: 0, page: 0, size: 20 },
      isLoading: false,
    })

    renderToStaticMarkup(<DownloadEventsPage />)

    expect(useDownloadEventsMock).toHaveBeenCalledWith({
      namespace: 'platform-tools',
      slug: undefined,
      version: undefined,
      userQuery: 'Brandon',
      source: 'cli',
      startTime: new Date('2026-07-05T00:00').toISOString(),
      endTime: new Date('2026-08-04T00:00').toISOString(),
      page: 0,
      size: 20,
    })
  })

  it('uses a legacy user ID route filter as the combined user query', () => {
    useSearchMock.mockReturnValue({ userId: 'legacy-user' })
    useDownloadEventsMock.mockReturnValue({
      data: { items: [], total: 0, page: 0, size: 20 },
      isLoading: false,
    })

    renderToStaticMarkup(<DownloadEventsPage />)

    expect(useDownloadEventsMock).toHaveBeenCalledWith(expect.objectContaining({
      userQuery: 'legacy-user',
    }))
  })
})

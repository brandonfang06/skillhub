import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

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
}))

vi.mock('@/shared/ui/card', () => ({
  Card: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/shared/ui/input', () => ({
  Input: () => null,
}))

vi.mock('@/shared/ui/button', () => ({
  Button: ({ children }: { children: unknown }) => children,
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
  useDownloadEvents: () => useDownloadEventsMock(),
}))

import { DownloadEventsPage } from './download-events'

describe('DownloadEventsPage', () => {
  it('renders the page title and empty state', () => {
    useDownloadEventsMock.mockReturnValue({
      data: { items: [], total: 0, page: 0, size: 20 },
      isLoading: false,
    })

    const html = renderToStaticMarkup(<DownloadEventsPage />)

    expect(html).toContain('downloadEvents.title')
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
    expect(html).toContain('skillhub-cli')
  })
})

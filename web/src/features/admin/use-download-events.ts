import { useQuery } from '@tanstack/react-query'
import { adminApi } from '@/api/client'
import type { DownloadEventItem, PagedResponse } from '@/api/types'

export interface DownloadEventParams {
  namespace?: string
  slug?: string
  version?: string
  userQuery?: string
  userId?: string
  source?: string
  startTime?: string
  endTime?: string
  page?: number
  size?: number
}

export type PagedDownloadEvents = PagedResponse<DownloadEventItem>

async function getDownloadEvents(params: DownloadEventParams): Promise<PagedDownloadEvents> {
  return adminApi.getDownloadEvents(params)
}

export function useDownloadEvents(params: DownloadEventParams) {
  return useQuery({
    queryKey: ['admin', 'download-events', params],
    queryFn: () => getDownloadEvents(params),
  })
}

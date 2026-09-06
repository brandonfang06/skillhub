import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { notificationApi } from '@/api/client'
import type { NotificationItem, PagedResponse } from '@/api/types'
import { decrementUnreadCount, resetUnreadCount } from './notification-unread-cache'
import { getNotificationQueryKeyScope } from './notification-session'

export const NOTIFICATION_QUERY_KEYS = {
  list: (userId?: string | null, page?: number, size?: number) => [...getNotificationQueryKeyScope(userId), 'list', page, size] as const,
  unreadCount: (userId?: string | null) => [...getNotificationQueryKeyScope(userId), 'unread-count'] as const,
  listByCategory: (userId?: string | null, page?: number, size?: number, category?: string) =>
    [...getNotificationQueryKeyScope(userId), 'list', page, size, category] as const,
}

export const NOTIFICATION_POLL_INTERVAL_MS = 10_000

const notificationPollingOptions = {
  staleTime: 0,
  refetchInterval: NOTIFICATION_POLL_INTERVAL_MS,
  refetchOnWindowFocus: true,
  refetchOnReconnect: true,
  retry: false,
} as const

export function getNotificationListQueryOptions(
  userId?: string | null,
  page = 0,
  size = 20,
  category?: string,
) {
  return {
    queryKey: NOTIFICATION_QUERY_KEYS.listByCategory(userId, page, size, category),
    queryFn: () => notificationApi.list({ page, size, category }) as Promise<PagedResponse<NotificationItem>>,
    enabled: !!userId,
    ...notificationPollingOptions,
  }
}

export function getUnreadCountQueryOptions(userId?: string | null) {
  return {
    queryKey: NOTIFICATION_QUERY_KEYS.unreadCount(userId),
    queryFn: () => notificationApi.getUnreadCount(),
    enabled: !!userId,
    ...notificationPollingOptions,
  }
}

/**
 * Fetches paginated notification list.
 */
export function useNotifications(userId?: string | null, page = 0, size = 5) {
  return useQuery(getNotificationListQueryOptions(userId, page, size))
}

/**
 * Fetches the current unread notification count for the badge.
 */
export function useUnreadCount(userId?: string | null) {
  return useQuery(getUnreadCountQueryOptions(userId))
}

/**
 * Fetches paginated notification list with optional category filter.
 */
export function useNotificationList(userId?: string | null, page = 0, size = 20, category?: string) {
  return useQuery(getNotificationListQueryOptions(userId, page, size, category))
}

/**
 * Marks all notifications as read and invalidates relevant queries.
 */
export function useMarkAllRead(userId?: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => notificationApi.markAllRead(),
    onSuccess: () => {
      resetUnreadCount(queryClient, userId)
      void queryClient.invalidateQueries({ queryKey: getNotificationQueryKeyScope(userId) })
    },
  })
}

/**
 * Marks a single notification as read and invalidates relevant queries.
 */
export function useMarkRead(userId?: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => notificationApi.markRead(id),
    onSuccess: () => {
      decrementUnreadCount(queryClient, userId)
      void queryClient.invalidateQueries({ queryKey: getNotificationQueryKeyScope(userId) })
    },
  })
}

export function useDeleteReadNotification(userId?: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => notificationApi.deleteRead(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: getNotificationQueryKeyScope(userId) })
    },
  })
}

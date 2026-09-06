import { describe, expect, it } from 'vitest'
import {
  NOTIFICATION_POLL_INTERVAL_MS,
  getNotificationListQueryOptions,
  getUnreadCountQueryOptions,
} from './use-notifications'

describe('notification polling query options', () => {
  it('polls authenticated user scopes every ten seconds and refreshes on focus/reconnect', () => {
    const unread = getUnreadCountQueryOptions('user-a')
    const list = getNotificationListQueryOptions('user-a', 0, 20, 'REVIEW')

    for (const options of [unread, list]) {
      expect(options.enabled).toBe(true)
      expect(options.refetchInterval).toBe(NOTIFICATION_POLL_INTERVAL_MS)
      expect(options.refetchOnWindowFocus).toBe(true)
      expect(options.refetchOnReconnect).toBe(true)
      expect(options.retry).toBe(false)
    }
    expect(unread.queryKey).toEqual(['notifications', 'user-a', 'unread-count'])
    expect(list.queryKey).toEqual(['notifications', 'user-a', 'list', 0, 20, 'REVIEW'])
  })

  it('does not poll without an authenticated identity', () => {
    expect(getUnreadCountQueryOptions(null).enabled).toBe(false)
    expect(getNotificationListQueryOptions(undefined, 0, 5).enabled).toBe(false)
  })
})

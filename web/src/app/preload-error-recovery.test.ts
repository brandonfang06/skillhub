import { describe, expect, it, vi, type Mock } from 'vitest'
import {
  PRELOAD_ERROR_RELOAD_KEY,
  PRELOAD_ERROR_RETRY_WINDOW_MS,
  recoverFromPreloadError,
  type PreloadRecoveryRuntime,
  type VitePreloadErrorEvent,
} from './preload-error-recovery'

function createPreloadErrorEvent(message: string): VitePreloadErrorEvent {
  const event = new Event('vite:preloadError', { cancelable: true }) as VitePreloadErrorEvent
  event.payload = new Error(message)
  return event
}

function createRuntime(now = 1_000): PreloadRecoveryRuntime & {
  reload: Mock<() => void>
} {
  const values = new Map<string, string>()

  return {
    storage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => {
        values.set(key, value)
      },
    },
    now: () => now,
    reload: vi.fn(),
  }
}

describe('recoverFromPreloadError', () => {
  it('prevents the first stale chunk error and reloads the current page', () => {
    const runtime = createRuntime()
    const event = createPreloadErrorEvent(
      'Failed to fetch dynamically imported module: /assets/review-detail-old.js',
    )

    expect(recoverFromPreloadError(event, runtime)).toBe(true)
    expect(event.defaultPrevented).toBe(true)
    expect(runtime.reload).toHaveBeenCalledOnce()
    expect(runtime.storage.getItem(PRELOAD_ERROR_RELOAD_KEY)).toContain('review-detail-old.js')
  })

  it('does not reload repeatedly for the same failed chunk within the guard window', () => {
    const runtime = createRuntime()
    const message = 'Failed to fetch dynamically imported module: /assets/review-detail-old.js'

    expect(recoverFromPreloadError(createPreloadErrorEvent(message), runtime)).toBe(true)

    const repeatedEvent = createPreloadErrorEvent(message)
    expect(recoverFromPreloadError(repeatedEvent, runtime)).toBe(false)
    expect(repeatedEvent.defaultPrevented).toBe(false)
    expect(runtime.reload).toHaveBeenCalledOnce()
  })

  it('permits a later recovery attempt after the guard window', () => {
    let currentTime = 1_000
    const runtime = createRuntime()
    runtime.now = () => currentTime
    const message = 'Failed to fetch dynamically imported module: /assets/review-detail-old.js'

    expect(recoverFromPreloadError(createPreloadErrorEvent(message), runtime)).toBe(true)
    currentTime += PRELOAD_ERROR_RETRY_WINDOW_MS + 1
    expect(recoverFromPreloadError(createPreloadErrorEvent(message), runtime)).toBe(true)
    expect(runtime.reload).toHaveBeenCalledTimes(2)
  })

  it('leaves the error visible when session storage cannot guard against a reload loop', () => {
    const runtime = createRuntime()
    runtime.storage.getItem = () => {
      throw new Error('storage unavailable')
    }
    const event = createPreloadErrorEvent(
      'Failed to fetch dynamically imported module: /assets/review-detail-old.js',
    )

    expect(recoverFromPreloadError(event, runtime)).toBe(false)
    expect(event.defaultPrevented).toBe(false)
    expect(runtime.reload).not.toHaveBeenCalled()
  })
})

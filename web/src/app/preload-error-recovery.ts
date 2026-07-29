export const PRELOAD_ERROR_RELOAD_KEY = 'skillhub:preload-error-reload'
export const PRELOAD_ERROR_RETRY_WINDOW_MS = 60_000
export interface VitePreloadErrorEvent extends Event {
  payload: unknown
}

interface PreloadRecoveryStorage {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
}

export interface PreloadRecoveryRuntime {
  storage: PreloadRecoveryStorage
  now: () => number
  reload: () => void
}

interface PreloadRecoveryAttempt {
  fingerprint: string
  attemptedAt: number
}

function getErrorFingerprint(payload: unknown): string {
  if (payload instanceof Error) {
    return `${payload.name}:${payload.message}`
  }
  if (typeof payload === 'string') {
    return payload
  }

  try {
    return JSON.stringify(payload)
  } catch {
    return String(payload)
  }
}

function readPreviousAttempt(storage: PreloadRecoveryStorage): PreloadRecoveryAttempt | null {
  const rawAttempt = storage.getItem(PRELOAD_ERROR_RELOAD_KEY)
  if (!rawAttempt) {
    return null
  }

  const attempt = JSON.parse(rawAttempt) as Partial<PreloadRecoveryAttempt>
  if (typeof attempt.fingerprint !== 'string' || typeof attempt.attemptedAt !== 'number') {
    return null
  }

  return {
    fingerprint: attempt.fingerprint,
    attemptedAt: attempt.attemptedAt,
  }
}

export function recoverFromPreloadError(
  event: VitePreloadErrorEvent,
  runtime: PreloadRecoveryRuntime,
): boolean {
  const fingerprint = getErrorFingerprint(event.payload)
  const attemptedAt = runtime.now()

  try {
    const previousAttempt = readPreviousAttempt(runtime.storage)
    const elapsed = previousAttempt ? attemptedAt - previousAttempt.attemptedAt : null
    if (
      previousAttempt?.fingerprint === fingerprint
      && elapsed !== null
      && elapsed >= 0
      && elapsed <= PRELOAD_ERROR_RETRY_WINDOW_MS
    ) {
      return false
    }

    runtime.storage.setItem(
      PRELOAD_ERROR_RELOAD_KEY,
      JSON.stringify({ fingerprint, attemptedAt } satisfies PreloadRecoveryAttempt),
    )
  } catch {
    return false
  }

  event.preventDefault()
  runtime.reload()
  return true
}

export function installPreloadErrorRecovery(): () => void {
  const handlePreloadError = (event: Event) => {
    recoverFromPreloadError(event as VitePreloadErrorEvent, {
      storage: window.sessionStorage,
      now: () => Date.now(),
      reload: () => window.location.reload(),
    })
  }

  window.addEventListener('vite:preloadError', handlePreloadError)
  return () => window.removeEventListener('vite:preloadError', handlePreloadError)
}

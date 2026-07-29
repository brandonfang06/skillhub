import { expect, test } from '@playwright/test'
import { PRELOAD_ERROR_RELOAD_KEY } from '../src/app/preload-error-recovery'

const STALE_CHUNK_ERROR =
  'Failed to fetch dynamically imported module: /assets/review-detail-stale.js'

test('reloads once for a stale route chunk without entering a reload loop', async ({ page }) => {
  await page.goto('/')
  await page.evaluate((storageKey) => sessionStorage.removeItem(storageKey), PRELOAD_ERROR_RELOAD_KEY)

  const reload = page.waitForEvent(
    'framenavigated',
    (frame) => frame === page.mainFrame(),
  )
  await page.evaluate((message) => {
    window.setTimeout(() => {
      const event = new Event('vite:preloadError', { cancelable: true }) as Event & {
        payload: Error
      }
      event.payload = new Error(message)
      window.dispatchEvent(event)
    }, 0)
  }, STALE_CHUNK_ERROR)
  await reload
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(250)

  const storedAttempt = await page.evaluate(
    (storageKey) => sessionStorage.getItem(storageKey),
    PRELOAD_ERROR_RELOAD_KEY,
  )
  expect(storedAttempt).toContain('review-detail-stale.js')

  let repeatedNavigation = false
  const recordNavigation = () => {
    repeatedNavigation = true
  }
  page.on('framenavigated', recordNavigation)
  const repeatedEventPrevented = await page.evaluate((message) => {
    const event = new Event('vite:preloadError', { cancelable: true }) as Event & {
      payload: Error
    }
    event.payload = new Error(message)
    window.dispatchEvent(event)
    return event.defaultPrevented
  }, STALE_CHUNK_ERROR)
  await page.waitForTimeout(500)
  page.off('framenavigated', recordNavigation)

  expect(repeatedEventPrevented).toBe(false)
  expect(repeatedNavigation).toBe(false)
})

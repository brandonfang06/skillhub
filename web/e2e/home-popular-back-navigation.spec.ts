import { expect, test } from '@playwright/test'
import { setEnglishLocale } from './helpers/auth-fixtures'
import { registerSession } from './helpers/session'

const viewports = [
  { name: 'desktop', width: 1280, height: 720 },
  { name: 'mobile', width: 390, height: 844 },
]

for (const viewport of viewports) {
  test(`popular downloads remains visible after returning from skill detail on ${viewport.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport)
    await setEnglishLocale(page)
    await registerSession(page, testInfo)

    let popularRequestCount = 0
    page.on('response', (response) => {
      if (response.url().includes('/api/web/skills?sort=downloads&size=6')) {
        popularRequestCount += 1
      }
    })

    await page.goto('/')
    const heading = page.getByRole('heading', { name: 'Popular Downloads' })
    const section = page.locator('section').filter({ has: heading })
    const cards = section.getByRole('link')
    await section.scrollIntoViewIfNeeded()
    await expect(cards.first()).toBeVisible({ timeout: 10_000 })

    await cards.first().click()
    await expect(page).toHaveURL(/\/space\//)
    await page.goBack()
    await expect(page).toHaveURL(/\/$/)
    await page.waitForTimeout(2_000)

    const diagnostics = await section.evaluate((element) => {
      const style = window.getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return {
        animations: element.getAnimations().map((animation) => ({
          currentTime: animation.currentTime,
          id: animation.id,
          playState: animation.playState,
          timing: (animation.effect as KeyframeEffect | null)?.getComputedTiming(),
        })),
        animationDelay: style.animationDelay,
        animationName: style.animationName,
        animationPlayState: style.animationPlayState,
        animationTimingFunction: style.animationTimingFunction,
        cardCount: element.querySelectorAll('[role="link"]').length,
        className: element.className,
        display: style.display,
        inlineStyle: element.getAttribute('style'),
        opacity: style.opacity,
        rect: {
          bottom: rect.bottom,
          height: rect.height,
          top: rect.top,
        },
        scrollY: window.scrollY,
        visibility: style.visibility,
      }
    })

    expect(
      diagnostics,
      `popular requests: ${popularRequestCount}; diagnostics: ${JSON.stringify(diagnostics)}`,
    ).toMatchObject({
      cardCount: 6,
      display: 'block',
      opacity: '1',
      visibility: 'visible',
    })
    await expect(section).toBeVisible()
    await expect(cards.first()).toBeVisible()
  })
}

import { describe, expect, it } from 'vitest'

import { isRectVisibleInViewport } from './use-in-view'

describe('useInView', () => {
  it('exports a function', async () => {
    const mod = await import('./use-in-view')
    expect(typeof mod.useInView).toBe('function')
  })

  it('treats an already-visible section as in view', () => {
    expect(
      isRectVisibleInViewport({ top: 580, bottom: 680, height: 100 }, 600, 0.15),
    ).toBe(true)
  })

  it('does not reveal a section that has not reached the viewport threshold', () => {
    expect(
      isRectVisibleInViewport({ top: 590, bottom: 690, height: 100 }, 600, 0.15),
    ).toBe(false)
  })
})

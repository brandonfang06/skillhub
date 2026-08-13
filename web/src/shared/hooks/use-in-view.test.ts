// @vitest-environment jsdom

import { act, render } from '@testing-library/react'
import { createElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { isRectVisibleInViewport, useInView } from './use-in-view'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

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

  it('reveals a section when browser history restores it into the viewport', () => {
    let rect = { top: 900, bottom: 1000, height: 100 }
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
      () => rect as DOMRect,
    )
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )

    function Section() {
      const { ref, inView } = useInView()
      return createElement('section', {
        'data-testid': 'section',
        'data-visible': inView,
        ref,
      })
    }

    const view = render(createElement(Section))
    expect(view.getByTestId('section').getAttribute('data-visible')).toBe('false')

    rect = { top: 200, bottom: 300, height: 100 }
    act(() => window.dispatchEvent(new Event('scroll')))

    expect(view.getByTestId('section').getAttribute('data-visible')).toBe('true')
  })
})

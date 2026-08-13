import { useEffect, useRef, useState } from 'react'

type ViewportRect = Pick<DOMRectReadOnly, 'top' | 'bottom' | 'height'>

export function isRectVisibleInViewport(
  rect: ViewportRect,
  viewportHeight: number,
  threshold = 0.15,
) {
  if (viewportHeight <= 0 || rect.bottom <= 0 || rect.top >= viewportHeight) {
    return false
  }

  const visibleHeight = Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0)
  if (visibleHeight <= 0) {
    return false
  }

  if (rect.height <= 0) {
    return true
  }

  return visibleHeight / rect.height >= threshold
}

function getFirstThreshold(threshold: IntersectionObserverInit['threshold'] | undefined) {
  if (Array.isArray(threshold)) {
    return threshold[0] ?? 0.15
  }

  return threshold ?? 0.15
}

function getViewportHeight() {
  return window.innerHeight || document.documentElement.clientHeight
}

export function useInView(options?: IntersectionObserverInit) {
  const ref = useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)
  const optionsRef = useRef(options)

  useEffect(() => {
    optionsRef.current = options
  }, [options])

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observerOptions = { threshold: 0.15, ...optionsRef.current }
    let observer: IntersectionObserver | null = null
    let frame = 0
    let delayedCheck = 0
    let revealed = false

    const stopFallbackChecks = () => {
      window.removeEventListener('scroll', revealIfVisible)
      window.removeEventListener('resize', revealIfVisible)
      window.removeEventListener('pageshow', revealIfVisible)
      window.cancelAnimationFrame(frame)
      window.clearTimeout(delayedCheck)
    }

    const reveal = () => {
      if (revealed) return

      revealed = true
      setInView(true)
      observer?.unobserve(el)
      stopFallbackChecks()
    }

    const revealIfVisible = () => {
      if (
        isRectVisibleInViewport(
          el.getBoundingClientRect(),
          getViewportHeight(),
          getFirstThreshold(observerOptions.threshold),
        )
      ) {
        reveal()
        return true
      }

      return false
    }

    if (revealIfVisible()) {
      return
    }

    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }

    observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          reveal()
        }
      },
      observerOptions,
    )

    observer.observe(el)
    window.addEventListener('scroll', revealIfVisible, { passive: true })
    window.addEventListener('resize', revealIfVisible)
    window.addEventListener('pageshow', revealIfVisible)
    frame = window.requestAnimationFrame(revealIfVisible)
    delayedCheck = window.setTimeout(revealIfVisible, 250)

    return () => {
      stopFallbackChecks()
      observer?.disconnect()
    }
  }, [])

  return { ref, inView }
}

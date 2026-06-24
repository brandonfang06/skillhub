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
    const revealIfVisible = () => {
      if (
        isRectVisibleInViewport(
          el.getBoundingClientRect(),
          getViewportHeight(),
          getFirstThreshold(observerOptions.threshold),
        )
      ) {
        setInView(true)
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

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          observer.unobserve(el)
        }
      },
      observerOptions,
    )

    observer.observe(el)
    const frame = window.requestAnimationFrame(() => {
      if (revealIfVisible()) {
        observer.unobserve(el)
      }
    })

    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [])

  return { ref, inView }
}

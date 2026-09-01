import { describe, expect, it } from 'vitest'

import indexHtml from '../../index.html?raw'

describe('playground content security policy', () => {
  it('allows an operator-configured HTTPS sidecar origin', () => {
    const policy = indexHtml.match(/connect-src ([^;]+);/)?.[1] ?? ''

    expect(policy.split(/\s+/)).toContain('https:')
  })

  it('loads self-hosted fonts through a subpath-safe relative URL', () => {
    expect(indexHtml).toContain('href="./fonts/fonts.css"')
    expect(indexHtml).not.toContain('fonts.googleapis.com')
    expect(indexHtml).not.toContain('fonts.gstatic.com')
  })
})

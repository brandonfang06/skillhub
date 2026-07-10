import { describe, expect, it } from 'vitest'

import indexHtml from '../../index.html?raw'

describe('playground content security policy', () => {
  it('allows an operator-configured HTTPS sidecar origin', () => {
    const policy = indexHtml.match(/connect-src ([^;]+);/)?.[1] ?? ''

    expect(policy.split(/\s+/)).toContain('https:')
  })
})

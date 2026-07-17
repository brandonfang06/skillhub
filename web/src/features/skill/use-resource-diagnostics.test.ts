import { describe, expect, it } from 'vitest'
import { useResourceDiagnostics } from './use-resource-diagnostics'

describe('useResourceDiagnostics', () => {
  it('exports the bounded admin diagnostics query hook', () => {
    expect(useResourceDiagnostics).toBeTypeOf('function')
  })
})

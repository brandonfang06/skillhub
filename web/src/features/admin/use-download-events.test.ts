import { describe, expect, it } from 'vitest'
import * as downloadEvents from './use-download-events'

describe('use-download-events module exports', () => {
  it('exports the useDownloadEvents query hook', () => {
    expect(downloadEvents.useDownloadEvents).toBeTypeOf('function')
  })
})

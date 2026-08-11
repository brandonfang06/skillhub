import { describe, expect, it } from 'vitest'
import { scanStatusRefetchInterval } from './scan-status-polling'

describe('scanStatusRefetchInterval', () => {
  it('polls skill pages while any visible version is scanning', () => {
    expect(scanStatusRefetchInterval({
      items: [
        { ownerPreviewVersion: { status: 'PENDING_REVIEW' } },
        { ownerPreviewVersion: { status: 'SCANNING' } },
      ],
    })).toBe(3_000)

    expect(scanStatusRefetchInterval([
      { status: 'PUBLISHED' },
      { status: 'SCANNING' },
    ])).toBe(3_000)
  })

  it('stops polling after all versions reach terminal states', () => {
    expect(scanStatusRefetchInterval({
      headlineVersion: { status: 'SCAN_FAILED' },
      ownerPreviewVersion: { status: 'SCAN_FAILED' },
    })).toBe(false)

    expect(scanStatusRefetchInterval([
      { status: 'PUBLISHED' },
      { status: 'PENDING_REVIEW' },
    ])).toBe(false)
  })
})

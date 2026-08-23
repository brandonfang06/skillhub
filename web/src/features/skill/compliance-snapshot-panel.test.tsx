/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ComplianceSnapshotPanel } from './compliance-snapshot-panel'

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next')
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, number>) =>
        key === 'compliance.mappingCount'
          ? `${values?.count} mappings`
          : key,
    }),
  }
})

const snapshot = {
  schemaVersion: '1.0',
  digest: 'sha256:123456789012345678901234567890',
  items: [
    {
      standard: 'mitre-attack',
      version: 'v19.1',
      controlId: 'T1059',
      title: 'Command and Scripting Interpreter',
      evidence: [
        {
          type: 'external-url',
          url: 'https://example.test/a/really/long/evidence/location/that/must/wrap',
          sha256: 'a'.repeat(64),
        },
      ],
    },
    { standard: 'nist-csf', version: '2.0', controlId: 'PR.DS-01', evidence: [] },
    { standard: 'soc2', version: '2023', controlId: 'CC6.1', evidence: [] },
  ],
}

describe('ComplianceSnapshotPanel', () => {
  afterEach(cleanup)

  it('renders nothing when no publisher declarations exist', () => {
    expect(renderToStaticMarkup(
      <ComplianceSnapshotPanel snapshot={{ schemaVersion: '1.0', items: [], digest: 'sha256:empty' }} />,
    )).toBe('')
  })

  it('labels declarations as unverified publisher claims and exposes an accessible disclosure', () => {
    render(<ComplianceSnapshotPanel snapshot={snapshot} />)

    expect(screen.getByText((_, element) => (
      element?.tagName === 'P'
      && element.textContent?.includes('compliance.publisherClaimNotice') === true
    ))).toBeTruthy()
    expect(screen.getByText('mitre-attack · T1059')).toBeTruthy()
    expect(screen.getByText('+1')).toBeTruthy()
    expect(screen.queryByText(snapshot.items[0].evidence[0].url)).toBeNull()

    const toggle = screen.getByRole('button', { name: 'common.expand' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(toggle.getAttribute('aria-controls')).toBeTruthy()
    const controlledId = toggle.getAttribute('aria-controls') ?? ''
    expect(document.getElementById(controlledId)).toBeTruthy()
    fireEvent.keyDown(toggle, { key: 'Enter' })
    fireEvent.click(toggle)

    expect(screen.getByRole('button', { name: 'common.collapse' }).getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByRole('button', { name: 'common.collapse' }).getAttribute('aria-controls')).toBe(controlledId)
    expect(screen.getByText(snapshot.items[0].evidence[0].url)).toBeTruthy()
  })

  it('uses wrapping-safe classes for long evidence URLs and hashes at mobile widths', () => {
    render(<ComplianceSnapshotPanel snapshot={snapshot} defaultExpanded />)

    const evidence = screen.getByText(snapshot.items[0].evidence[0].url)
    const digest = screen.getByText(snapshot.digest)
    expect(evidence.className).toContain('break-all')
    expect(digest.className).toContain('break-all')
    expect(evidence.closest('[data-compliance-evidence]')?.className).toContain('min-w-0')
  })

  it('does not mount a maximum-size detail tree until expanded', () => {
    const maximumSnapshot = {
      schemaVersion: '1.0',
      digest: `sha256:${'d'.repeat(64)}`,
      items: Array.from({ length: 50 }, (_, mappingIndex) => ({
        standard: 'soc2',
        version: '2026',
        controlId: `CC${mappingIndex}`,
        evidence: Array.from({ length: 10 }, (_, evidenceIndex) => ({
          type: 'packaged-file',
          path: `evidence/${mappingIndex}/${evidenceIndex}.md`,
          sha256: `${mappingIndex}-${evidenceIndex}-${'a'.repeat(64)}`,
        })),
      })),
    }

    render(<ComplianceSnapshotPanel snapshot={maximumSnapshot} />)
    const toggle = screen.getByRole('button', { name: 'common.expand' })
    const controlledId = toggle.getAttribute('aria-controls') ?? ''

    expect(document.getElementById(controlledId)).toBeTruthy()
    expect(document.querySelectorAll('[data-compliance-evidence]')).toHaveLength(0)
    expect(screen.queryByText('evidence/49/9.md')).toBeNull()

    fireEvent.click(toggle)

    expect(screen.getByRole('button', { name: 'common.collapse' }).getAttribute('aria-controls')).toBe(controlledId)
    expect(document.querySelectorAll('[data-compliance-evidence]')).toHaveLength(500)
    expect(screen.getByText('evidence/49/9.md')).toBeTruthy()
  })
})

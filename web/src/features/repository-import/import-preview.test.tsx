import { describe, expect, it } from 'vitest'

import {
  buildDefaultCandidateSelection,
  buildIngestSelections,
} from './import-preview'

const candidate = {
  candidateId: 1,
  sourcePath: 'skills/Alpha Skill',
  detectedName: 'Alpha Skill',
  detectedDescription: 'First',
  sourceVersion: '0.1.0',
  state: 'DISCOVERED' as const,
  warnings: [],
}

describe('repository import preview helpers', () => {
  it('builds a safe editable default without selecting automatically', () => {
    expect(buildDefaultCandidateSelection(candidate)).toEqual({
      selected: false,
      targetSlug: 'alpha-skill',
      targetVersion: '0.1.0',
      visibility: 'NAMESPACE_ONLY',
    })
  })

  it('emits only explicit complete selections', () => {
    expect(
      buildIngestSelections(
        [candidate],
        {
          1: {
            selected: true,
            targetSlug: 'alpha',
            targetVersion: '1.0.0',
            visibility: 'NAMESPACE_ONLY',
          },
        },
      ),
    ).toEqual([
      {
        candidateId: 1,
        targetSlug: 'alpha',
        targetVersion: '1.0.0',
        visibility: 'NAMESPACE_ONLY',
      },
    ])
    expect(
      buildIngestSelections(
        [candidate],
        {
          1: {
            selected: true,
            targetSlug: '../bad',
            targetVersion: 'latest',
            visibility: 'NAMESPACE_ONLY',
          },
        },
      ),
    ).toEqual([])
  })
})

// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { CollectionCard } from './collection-card'

const collection = {
  collectionId: 1,
  namespace: 'opensource',
  slug: 'superpowers',
  displayName: 'Superpowers',
  summary: 'A curated agent workflow',
  status: 'ACTIVE' as const,
  hidden: false,
  canCurate: true,
  latestPublishedVersion: {
    versionId: 10,
    version: '1.4.0',
    status: 'PUBLISHED' as const,
    draftRevision: 0,
    memberCount: 12,
    createdAt: '2026-07-27T00:00:00Z',
  },
  draft: {
    versionId: 11,
    version: 'DRAFT',
    status: 'DRAFT' as const,
    draftRevision: 2,
    memberCount: 13,
    createdAt: '2026-07-27T00:00:00Z',
  },
  createdAt: '2026-07-27T00:00:00Z',
  updatedAt: '2026-07-27T00:00:00Z',
}

describe('CollectionCard', () => {
  it('renders collection metadata using the shared card visual language', () => {
    render(<CollectionCard collection={collection} />)

    expect(screen.getByText('Superpowers')).toBeTruthy()
    expect(screen.getByText('@opensource/superpowers')).toBeTruthy()
    expect(screen.getByText('A curated agent workflow')).toBeTruthy()
    expect(screen.getByText('v1.4.0')).toBeTruthy()
    expect(screen.getByText('12 collectionCard.members')).toBeTruthy()
    expect(screen.getByText('collectionCard.draft')).toBeTruthy()
  })

  it('activates from click, Enter, and Space', () => {
    const onClick = vi.fn()
    render(<CollectionCard collection={collection} onClick={onClick} />)
    const card = screen.getByRole('link')

    fireEvent.click(card)
    fireEvent.keyDown(card, { key: 'Enter' })
    fireEvent.keyDown(card, { key: ' ' })

    expect(onClick).toHaveBeenCalledTimes(3)
  })
})

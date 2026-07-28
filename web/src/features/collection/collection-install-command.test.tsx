import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

import {
  buildCollectionInstallCommand,
  CollectionInstallCommand,
} from './collection-install-command'

const input = {
  npmRegistry: 'https://nexus.example/npm-group',
  packageName: '@company/skillhub',
  cliVersion: '0.2.0',
  skillhubBaseUrl: 'https://skills.example.com',
  namespace: 'opensource',
  collection: 'superpowers',
  collectionVersion: '1.4.0',
}

describe('buildCollectionInstallCommand', () => {
  it('builds an immutable two-registry collection install command', () => {
    expect(buildCollectionInstallCommand(input)).toBe(
      'npx --yes --registry https://nexus.example/npm-group @company/skillhub@0.2.0 collection install @opensource/superpowers --registry https://skills.example.com --version 1.4.0 --scope user',
    )
  })

  it.each([
    { ...input, npmRegistry: '' },
    { ...input, npmRegistry: '/npm' },
    { ...input, packageName: 'bad package' },
    { ...input, cliVersion: 'latest' },
    { ...input, cliVersion: '^0.2.0' },
    { ...input, skillhubBaseUrl: 'javascript:alert(1)' },
    { ...input, namespace: '../admin' },
    { ...input, collectionVersion: 'next' },
  ])('rejects incomplete or unsafe input', (candidate) => {
    expect(buildCollectionInstallCommand(candidate)).toBeNull()
  })
})

describe('CollectionInstallCommand', () => {
  it('renders a readonly command and accessible copy control', () => {
    const html = renderToStaticMarkup(<CollectionInstallCommand input={input} />)
    expect(html).toContain('@company/skillhub@0.2.0')
    expect(html).toContain('collectionInstall.copy')
    expect(html).toContain('<code')
  })

  it('renders an unavailable message when configuration is incomplete', () => {
    const html = renderToStaticMarkup(
      <CollectionInstallCommand input={{ ...input, cliVersion: 'latest' }} />,
    )
    expect(html).toContain('collectionInstall.unavailable')
  })
})

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function publicAsset(relativePath) {
  return readFileSync(fileURLToPath(new URL(`../../public/${relativePath}`, import.meta.url)))
}

describe('upstream static assets', () => {
  it.each([
    'fonts/inter-latin-400-normal.woff2',
    'fonts/inter-latin-500-normal.woff2',
    'fonts/inter-latin-600-normal.woff2',
    'fonts/inter-latin-700-normal.woff2',
    'fonts/inter-latin-ext-400-normal.woff2',
    'fonts/inter-latin-ext-500-normal.woff2',
    'fonts/inter-latin-ext-600-normal.woff2',
    'fonts/inter-latin-ext-700-normal.woff2',
    'fonts/jetbrains-mono-latin-400-normal.woff2',
    'fonts/jetbrains-mono-latin-500-normal.woff2',
    'fonts/jetbrains-mono-latin-ext-400-normal.woff2',
    'fonts/jetbrains-mono-latin-ext-500-normal.woff2',
  ])('ships a valid WOFF2 asset: %s', (path) => {
    expect(publicAsset(path).subarray(0, 4).toString('ascii')).toBe('wOF2')
  })

  it('ships font CSS and license provenance', () => {
    const fontCss = publicAsset('fonts/fonts.css').toString('utf8')
    expect(fontCss).toContain('@font-face')
    expect(fontCss).not.toMatch(/url\(['"]?\//)
    const license = publicAsset('fonts/LICENSE.md').toString('utf8')
    expect(license).toContain('Inter')
    expect(license).toContain('JetBrains Mono')
  })

  it('ships the generic OIDC provider icon used by login buttons', () => {
    expect(publicAsset('oidc-logo.svg').toString('utf8')).toContain('<svg')
  })
})

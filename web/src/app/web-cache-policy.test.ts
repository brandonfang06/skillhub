/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'
import nginxConfig from '../../nginx.conf.template?raw'

describe('web cache policy', () => {
  it('revalidates SPA responses while retaining immutable hashed assets', () => {
    expect(nginxConfig).toMatch(
      /location \/ \{[\s\S]*?Cache-Control "no-cache, must-revalidate";[\s\S]*?\}/,
    )
    expect(nginxConfig).toMatch(
      /location \/assets\/ \{[\s\S]*?Cache-Control "public, immutable";[\s\S]*?\}/,
    )
    expect(nginxConfig).toMatch(
      /location = \/runtime-config\.js \{[\s\S]*?Cache-Control "no-store";[\s\S]*?\}/,
    )
  })
})

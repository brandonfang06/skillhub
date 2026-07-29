import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  InstallCommand,
  buildInstallCommand,
  buildInstallTarget,
  buildSkillhubInstallCommand,
  getBaseUrl,
  getCliRegistryUrl,
} from './install-command'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

describe('install-command', () => {
  const originalWindow = globalThis.window

  function setMockWindow(runtimeConfig: {
    appBaseUrl?: string
    cliRegistryUrl?: string
  } = {}) {
    const location = {
      protocol: 'https:',
      host: 'fallback.example.com',
    } satisfies Pick<Location, 'protocol' | 'host'>

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      writable: true,
      value: {
        __SKILLHUB_RUNTIME_CONFIG__: runtimeConfig,
        location,
      } satisfies {
        location: Pick<Location, 'protocol' | 'host'>
      } & {
        __SKILLHUB_RUNTIME_CONFIG__: {
          appBaseUrl?: string
          cliRegistryUrl?: string
        }
      },
    })
  }

  afterEach(() => {
    if (originalWindow) {
      Object.defineProperty(globalThis, 'window', {
        configurable: true,
        writable: true,
        value: originalWindow,
      })
      return
    }
    Reflect.deleteProperty(globalThis, 'window')
  })

  it('uses the plain slug for the global namespace', () => {
    expect(buildInstallTarget('global', 'my-skill')).toBe('my-skill')
    expect(buildInstallCommand('global', 'my-skill', 'https://skill.xfyun.cn')).toBe(
      'npx clawhub install my-skill --registry https://skill.xfyun.cn',
    )
  })

  it('prefixes non-global namespaces in the install target', () => {
    expect(buildInstallTarget('team-alpha', 'my-skill')).toBe('team-alpha--my-skill')
    expect(buildInstallCommand('team-alpha', 'my-skill', 'https://skill.xfyun.cn')).toBe(
      'npx clawhub install team-alpha--my-skill --registry https://skill.xfyun.cn',
    )
  })

  it('builds a one-line SkillHub npx command for the global namespace', () => {
    expect(buildSkillhubInstallCommand('global', 'my-skill', 'https://skill.xfyun.cn')).toBe(
      'npx @astron-team/skillhub@latest install my-skill --registry https://skill.xfyun.cn',
    )
  })

  it('builds a one-line SkillHub npx command with namespace for team skills', () => {
    expect(buildSkillhubInstallCommand('team-alpha', 'my-skill', 'https://skill.xfyun.cn')).toBe(
      'npx @astron-team/skillhub@latest install my-skill --namespace team-alpha --registry https://skill.xfyun.cn',
    )
  })

  it('uses the runtime app base url when available', () => {
    setMockWindow({ appBaseUrl: 'https://app.example.com' })

    expect(getBaseUrl()).toBe('https://app.example.com')
  })

  it('falls back to the browser origin when the app base url is missing', () => {
    setMockWindow()
    expect(getBaseUrl()).toBe('https://fallback.example.com')
  })

  it('falls back to browser origin when app base url is localhost', () => {
    setMockWindow({ appBaseUrl: 'http://localhost' })
    expect(getBaseUrl()).toBe('https://fallback.example.com')
  })

  it('falls back to browser origin when app base url contains localhost', () => {
    setMockWindow({ appBaseUrl: 'http://localhost:8080' })
    expect(getBaseUrl()).toBe('https://fallback.example.com')
  })

  it('uses a normalized runtime CLI registry URL when configured', () => {
    setMockWindow({
      appBaseUrl: 'https://app.example.com',
      cliRegistryUrl: ' http://app.example.com/ ',
    })

    expect(getCliRegistryUrl()).toBe('http://app.example.com')
  })

  it('preserves and normalizes a valid registry path prefix', () => {
    setMockWindow({
      appBaseUrl: 'https://app.example.com',
      cliRegistryUrl: ' https://app.example.com/registry/ ',
    })

    expect(getCliRegistryUrl()).toBe('https://app.example.com/registry')
  })

  it.each([
    'https://app.example.com/registry&whoami',
    'https://app.example.com/registry;whoami',
    'https://app.example.com/registry|whoami',
    'https://app.example.com/registry$(whoami)',
    'https://app.example.com/registry`whoami`',
    'https://app.example.com/team%20registry',
    'https://app.example.com/team registry',
    'https://app.example.com/registry<input',
    'https://app.example.com/registry>output',
  ])('falls back to the app base URL for unsafe CLI registry path %j', (cliRegistryUrl) => {
    setMockWindow({
      appBaseUrl: 'https://app.example.com',
      cliRegistryUrl,
    })

    expect(getCliRegistryUrl()).toBe('https://app.example.com')
  })

  it.each(['', 'not-a-url', 'ftp://app.example.com'])(
    'falls back to the app base URL for invalid CLI registry URL %j',
    (cliRegistryUrl) => {
      setMockWindow({
        appBaseUrl: 'https://app.example.com',
        cliRegistryUrl,
      })

      expect(getCliRegistryUrl()).toBe('https://app.example.com')
    },
  )

  it.each([
    'https://user@app.example.com/registry',
    'https://:secret@app.example.com/registry',
    'https://app.example.com/registry?channel=internal',
    'https://app.example.com/registry#install',
  ])(
    'falls back to the app base URL for unsupported CLI registry URL %j',
    (cliRegistryUrl) => {
      setMockWindow({
        appBaseUrl: 'https://app.example.com',
        cliRegistryUrl,
      })

      expect(getCliRegistryUrl()).toBe('https://app.example.com')
    },
  )

  it('renders the install command in a more compact code block', () => {
    setMockWindow({ appBaseUrl: 'http://localhost:3000' })

    const html = renderToStaticMarkup(createElement(InstallCommand, { namespace: 'global', slug: 'meeting-minutes-generator' }))

    expect(html).toContain('px-4 py-3')
    expect(html).toContain('leading-relaxed')
    expect(html).toContain('break-all')
  })

  it('renders install method tabs with only a short active underline', () => {
    setMockWindow({ appBaseUrl: 'https://app.example.com' })

    const html = renderToStaticMarkup(createElement(InstallCommand, {
      namespace: 'global',
      slug: 'meeting-minutes-generator',
    }))

    expect(html).toContain('after:w-6')
    expect(html).toContain('after:h-0.5')
    expect(html).not.toContain('rounded-lg border bg-background/80 p-1')
    expect(html).not.toContain('flex-1 rounded-md')
  })

  it('renders only the SkillHub CLI install method', () => {
    setMockWindow({
      appBaseUrl: 'https://app.example.com',
      cliRegistryUrl: 'http://app.example.com',
    })

    const html = renderToStaticMarkup(createElement(InstallCommand, {
      namespace: 'team-alpha',
      slug: 'meeting-minutes-generator',
    }))

    expect(html).toContain('skillDetail.installMethodSkillhub')
    expect(html).toContain('npx @astron-team/skillhub@latest install meeting-minutes-generator --namespace team-alpha --registry http://app.example.com')
    expect(html).not.toContain('--registry https://app.example.com')
    expect(html).not.toContain('skillDetail.installMethodClawhub')
    expect(html).not.toContain('npx clawhub install team-alpha--meeting-minutes-generator --registry http://app.example.com')
  })
})

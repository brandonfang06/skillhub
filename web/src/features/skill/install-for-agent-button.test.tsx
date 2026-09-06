// @vitest-environment jsdom

import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { act, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InstallForAgentButton, buildAgentInstallPrompt } from './install-for-agent-button'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) => key === 'skillDetail.installForAgent.prompt'
      ? `Connect with ${values?.guideUrl}; install ${values?.skill} version ${values?.version} from ${values?.registryUrl}.`
      : key,
  }),
}))

describe('install-for-agent-button', () => {
  const originalRuntimeConfig = window.__SKILLHUB_RUNTIME_CONFIG__
  const formatPrompt = (guideUrl: string, skill: string, version: string, registryUrl: string) => (
    `Connect with ${guideUrl}; install ${skill} version ${version} from ${registryUrl}.`
  )

  afterEach(() => {
    vi.restoreAllMocks()
    window.__SKILLHUB_RUNTIME_CONFIG__ = originalRuntimeConfig
  })

  it('keeps browser guide and explicitly configured CLI registry URLs distinct', () => {
    expect(buildAgentInstallPrompt(
      'team-alpha',
      'my-skill',
      '2.0.0',
      'https://skill.example.com/skillhub/',
      'http://skillhub.internal/skillhub',
      formatPrompt,
    )).toBe(
      'Connect with https://skill.example.com/skillhub/install/skillhub.md; install @team-alpha/my-skill version 2.0.0 from http://skillhub.internal/skillhub.',
    )
  })

  it('renders an accessible button and disables unsafe or unavailable versions', () => {
    const enabled = renderToStaticMarkup(createElement(InstallForAgentButton, {
      namespace: 'global', slug: 'my-skill', version: '1.2.3',
    }))
    const unsafe = renderToStaticMarkup(createElement(InstallForAgentButton, {
      namespace: 'global', slug: 'my-skill', version: '1.0.0&echo INJECTED',
    }))
    const unavailable = renderToStaticMarkup(createElement(InstallForAgentButton, {
      namespace: 'global', slug: 'my-skill', version: '1.2.3', disabled: true,
    }))

    expect(enabled).toContain('data-testid="install-for-agent-button"')
    expect(enabled).toContain('aria-label="skillDetail.installForAgent.button"')
    expect(unsafe).toContain('disabled=""')
    expect(unavailable).toContain('disabled=""')
  })

  it('copies the fixed coordinate, version, guide and CLI registry', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    window.__SKILLHUB_RUNTIME_CONFIG__ = {
      appBaseUrl: 'https://skill.example.com/skillhub',
      cliRegistryUrl: 'http://skillhub.internal/skillhub',
    }

    const { getByTestId } = render(createElement(InstallForAgentButton, {
      namespace: 'team-alpha', slug: 'my-skill', version: '2.0.0',
    }))
    await act(async () => fireEvent.click(getByTestId('install-for-agent-button')))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      'Connect with https://skill.example.com/skillhub/install/skillhub.md; install @team-alpha/my-skill version 2.0.0 from http://skillhub.internal/skillhub.',
    ))
  })
})

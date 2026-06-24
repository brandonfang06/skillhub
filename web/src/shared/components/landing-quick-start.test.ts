import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import * as mod from './landing-quick-start'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => {
      const values: Record<string, string> = {
        'landing.quickStart.title': 'Quick Start',
        'landing.quickStart.description': 'Start with the internal SkillHub CLI.',
        'landing.quickStart.tabs.agent': 'I am Agent',
        'landing.quickStart.tabs.human': 'I am Human',
        'landing.quickStart.tabs.cli': 'CLI',
        'landing.quickStart.cli.description': 'Install the SkillHub CLI locally.',
        'landing.quickStart.cli.command': 'npm i -g @astron-team/skillhub',
        'copyButton.copy': 'Copy',
      }
      return values[key] ?? options?.defaultValue ?? key
    },
  }),
}))

describe('landing-quick-start module exports', () => {
  it('exports the LandingQuickStartSection component', () => {
    expect(mod.LandingQuickStartSection).toBeTypeOf('function')
  })

  it('renders only the CLI quick start while ClawHub-only tabs are disabled', () => {
    const html = renderToStaticMarkup(createElement(mod.LandingQuickStartSection))

    expect(html).toContain('CLI')
    expect(html).toContain('npm i -g @astron-team/skillhub')
    expect(html).not.toContain('I am Agent')
    expect(html).not.toContain('I am Human')
  })
})

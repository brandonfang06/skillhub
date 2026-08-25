import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import zh from './locales/zh.json'
import zhTW from './locales/zh-TW.json'

const SELECTION_KEYS = [
  'start',
  'selectSkill',
  'count',
  'limitReached',
  'clear',
  'continue',
] as const

const PAGE_KEYS = [
  'title',
  'subtitle',
  'backToSearch',
  'empty',
  'selectedHeading',
  'removeSkill',
  'scopeHeading',
  'scopeUser',
  'scopeProject',
  'projectWarning',
  'agentsHeading',
  'agentsHint',
  'genericUnsupported',
  'selectAgentRequired',
  'forceLabel',
  'forceHint',
  'forceWarning',
  'identityHeading',
  'identityHint',
  'commandsHeading',
  'commandsHint',
  'copyAll',
  'copyCommand',
  'resultHint',
] as const

describe('multi-skill install locale contract', () => {
  it.each([
    ['en', en],
    ['zh', zh],
    ['zh-TW', zhTW],
  ] as const)('defines every selection and install-page key in %s', (_name, locale) => {
    for (const key of SELECTION_KEYS) {
      expect(locale.installSelection[key]).toBeTruthy()
    }
    for (const key of PAGE_KEYS) {
      expect(locale.installSkills[key]).toBeTruthy()
    }
  })

  it('uses clear Traditional Chinese product wording', () => {
    expect(zhTW.installSelection.start).toBe('選取多個 Skills')
    expect(zhTW.installSkills.title).toBe('安裝 Skills')
    expect(zhTW.installSkills.copyAll).toBe('複製全部指令')
  })
})

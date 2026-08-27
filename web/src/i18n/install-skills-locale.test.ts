import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import zh from './locales/zh.json'
import zhTW from './locales/zh-TW.json'

const SELECTION_KEYS = [
  'start',
  'startHint',
  'selectSkill',
  'count',
  'limitReached',
  'clear',
  'continue',
] as const

const PAGE_KEYS = [
  'title',
  'backToSearch',
  'empty',
  'selectedHeading',
  'removeSkill',
  'targetsHeading',
  'modeHeading',
  'modeDirect',
  'modeInteractive',
  'interactiveWarning',
  'scopeHeading',
  'scopeUser',
  'scopeProject',
  'projectWarning',
  'agentsHeading',
  'agentPlaceholder',
  'selectAgentRequired',
  'commandsHeading',
  'commandsHint',
  'copyAll',
  'copyCommand',
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

  it.each([en, zh, zhTW])('removes retired Force and terminal-identity decision copy', (locale) => {
    expect(locale.installSkills).not.toHaveProperty('forceLabel')
    expect(locale.installSkills).not.toHaveProperty('identityHeading')
  })

  it('uses clear Traditional Chinese product wording', () => {
    expect(zhTW.installSelection.start).toBe('批次安裝多個 Skills')
    expect(zhTW.installSelection.startHint).toBe('一次選取最多 20 個，並複製安裝指令')
    expect(zhTW.installSkills.title).toBe('安裝 Skills')
    expect(zhTW.installSkills.copyAll).toBe('複製全部指令')
    expect(zhTW.installSkills.modeInteractive).toBe('終端機互動選擇')
    expect(zhTW.installSkills.interactiveWarning).toContain('每個 Skill')
    expect(zhTW.installSkills.interactiveWarning).toContain('Generic')
    expect(zhTW.installSkills.interactiveWarning).toContain('不適用於 CI')
  })
})

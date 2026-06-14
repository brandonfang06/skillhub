import { describe, expect, it } from 'vitest'
import zhTW from './locales/zh-TW.json'

describe('traditional chinese locale', () => {
  it('uses the approved UI terms', () => {
    expect(zhTW.nav.publish).toBe('發佈')
    expect(zhTW.publish.title).toBe('發佈技能')
    expect(zhTW.nav.dashboard).toBe('儀表板')
    expect(zhTW.token.createNew).toBe('創建新 Token')
    expect(zhTW.home.viewAll).toBe('查看全部 →')
    expect(zhTW.landing.hero.subtitle).toContain('建立')
    expect(zhTW.landing.quickStart.description).toContain('串接')
  })
})

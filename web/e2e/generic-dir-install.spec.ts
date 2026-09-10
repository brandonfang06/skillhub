import { expect, test } from '@playwright/test'

const username = process.env.GENERIC_SMOKE_USERNAME
const password = process.env.GENERIC_SMOKE_PASSWORD
const bases = process.env.GENERIC_SMOKE_WEB_URLS?.split(',') ?? []
test.skip(!username || !password || bases.length === 0, 'Requires disposable real-service fixtures and web URLs')

for (const base of bases) {
  for (const width of [1440, 390]) {
    test(`Generic directory ${base} ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 })
      await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
      await page.addInitScript(() => localStorage.setItem('i18nextLng', 'en'))
      const errors: string[] = []
      const failedResponses: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      page.on('response', (response) => {
        if (response.status() >= 400 && response.url().includes('/api/')) failedResponses.push(`${response.status()} ${response.url()}`)
      })
      const login = await page.request.post(`${base}/api/v1/auth/local/login`, { data: { username, password } })
      expect(login.ok()).toBeTruthy()
      const directPage = await page.request.get(`${base}/install`, { maxRedirects: 0 })
      expect(directPage.status()).toBe(200)
      expect(directPage.headers()['cache-control']).toContain('no-cache')
      const guide = await page.request.get(`${base}/install/skillhub.md`, { maxRedirects: 0 })
      expect(guide.status()).toBe(200)
      expect(guide.headers()['content-type']).toContain('text/plain')
      await page.goto(`${base}/search?q=&sort=relevance&page=0&starredOnly=false`)
      await page.getByRole('button', { name: 'Install multiple Skills', exact: true }).click()
      const choices = page.getByRole('checkbox', { name: /^Select / })
      await choices.nth(0).check()
      await choices.nth(1).check()
      await page.getByRole('button', { name: 'Continue to install', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Install Skills', exact: true })).toBeVisible()
      const agent = page.getByRole('combobox', { name: 'Agent targets' })
      await agent.selectOption('generic')
      await expect(page.getByText('Uses .agents/skills via --dir.', { exact: false })).toBeVisible()
      const commands = page.locator('pre code')
      await expect(commands).toHaveCount(2)
      for (const command of await commands.allTextContents()) {
        expect(command).toContain(`--registry ${base} --dir "$HOME/.agents/skills" --force`)
        expect(command).not.toMatch(/--agent|--scope/)
      }
      await page.getByRole('button', { name: 'Copy all commands', exact: true }).click()
      const clipboard = await page.evaluate(() => navigator.clipboard.readText())
      expect(clipboard.replace(/\r\n/g, '\n')).toBe((await commands.allTextContents()).join('\n'))
      await page.screenshot({ path: testInfo.outputPath('generic-user.png'), fullPage: true })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
      await page.getByRole('radio', { name: 'Project', exact: true }).check()
      await expect(commands.first()).toContainText('--dir "./.agents/skills" --force')
      await page.reload()
      await expect(agent).toHaveValue('generic')
      await expect(commands.first()).toContainText('--dir "./.agents/skills" --force')
      await page.getByRole('radio', { name: 'Terminal interactive', exact: true }).check()
      await expect(commands.first()).toContainText('--scope project --force')
      expect(await commands.first().textContent()).not.toContain('--dir')
      await page.getByRole('radio', { name: 'Direct Agent', exact: true }).check()
      await expect(agent).toHaveValue('generic')
      await agent.selectOption('codex')
      await expect(commands.first()).toContainText('--scope project --agent codex --force')
      expect(errors).toEqual([])
      expect(failedResponses).toEqual([])
    })
  }
}

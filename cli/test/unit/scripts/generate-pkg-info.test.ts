import { describe, expect, test } from 'bun:test'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

describe('generate-pkg-info script', () => {
  test('is idempotent when generated directory already exists', async () => {
    const cliRoot = fileURLToPath(new URL('../../../', import.meta.url))
    const generatedDir = `${cliRoot}src/generated`

    expect(existsSync(generatedDir)).toBe(true)

    const proc = Bun.spawn({
      cmd: [process.execPath, 'scripts/generate-pkg-info.ts'],
      cwd: cliRoot,
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const [stdout, stderr, exitCode] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ])

    expect(stderr.trim()).toBe('')
    expect(stdout).toContain('generated')
    expect(exitCode).toBe(0)
  })
})

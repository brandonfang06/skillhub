import { describe, expect, test } from 'bun:test'
import { mkdir, mkdtemp, realpath, rm, stat, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  applyCredentialPermissions,
  canonicalizeExistingPath,
  canonicalizePath,
  userStateDir
} from '../../../src/platform/paths'

describe('userStateDir', () => {
  test('throws when home is empty string', () => {
    expect(() => userStateDir('')).toThrow('Cannot resolve user home directory')
  })
})

describe('applyCredentialPermissions', () => {
  test('sets 0o600 on unix', async () => {
    const tempDir = await mkdtemp(join(tmpdir(), 'skillhub-test-'))
    const tempFile = join(tempDir, 'credential.json')
    await writeFile(tempFile, '{}')

    await applyCredentialPermissions(tempFile)

    if (process.platform !== 'win32') {
      const stats = await stat(tempFile)
      expect(stats.mode & 0o777).toBe(0o600)
    }
  })
})

describe('canonicalizeExistingPath', () => {
  test('resolves an existing linked directory and preserves a missing path', async () => {
    const tempDir = await mkdtemp(join(tmpdir(), 'skillhub-paths-'))
    const target = join(tempDir, 'target')
    const alias = join(tempDir, 'alias')
    const missing = join(tempDir, 'missing')

    try {
      await mkdir(target)
      await symlink(target, alias, process.platform === 'win32' ? 'junction' : 'dir')

      expect(await canonicalizeExistingPath(alias)).toBe(await realpath(target))
      expect(await canonicalizeExistingPath(missing)).toBe(missing)
    } finally {
      await rm(tempDir, { recursive: true, force: true })
    }
  })
})

describe('canonicalizePath', () => {
  test('resolves the nearest existing ancestor of a missing path', async () => {
    const tempDir = await mkdtemp(join(tmpdir(), 'skillhub-paths-'))
    const target = join(tempDir, 'target')
    const alias = join(tempDir, 'alias')

    try {
      await mkdir(target)
      await symlink(target, alias, process.platform === 'win32' ? 'junction' : 'dir')

      expect(await canonicalizePath(join(alias, 'missing', 'skills')))
        .toBe(join(await realpath(target), 'missing', 'skills'))
    } finally {
      await rm(tempDir, { recursive: true, force: true })
    }
  })
})

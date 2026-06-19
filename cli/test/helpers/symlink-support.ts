import { mkdirSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export function canCreateDirectorySymlink(): boolean {
  const root = mkdtempSync(join(tmpdir(), 'skillhub-symlink-check-'))
  const target = join(root, 'target')
  const link = join(root, 'link')

  try {
    mkdirSync(target)
    symlinkSync(target, link, 'dir')
    return true
  } catch (error) {
    const code = errorCode(error)
    if (code === 'EPERM' || code === 'EACCES' || code === 'ENOTSUP') {
      return false
    }
    throw error
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
}

function errorCode(error: unknown): string | undefined {
  if (typeof error === 'object' && error !== null && 'code' in error) {
    const code = (error as { code?: unknown }).code
    return typeof code === 'string' ? code : undefined
  }
  return undefined
}

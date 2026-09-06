import { createHash } from 'node:crypto'
import { chmod, lstat, mkdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { lock } from 'proper-lockfile'
import { canonicalizeExistingPath } from '../platform/paths'
import { CliError } from '../shared/errors'
import { EXIT } from '../shared/constants'

/** Serializes every local lifecycle mutation for one Skill target directory. */
export async function acquireSkillTargetLock(rootDir: string, slug: string): Promise<() => Promise<void>> {
  const lockPath = await skillTargetLockPath(rootDir, slug)
  const recoveryLockPath = `${lockPath}.recovery`
  let releaseRecoveryLock: (() => Promise<void>) | undefined
  try {
    releaseRecoveryLock = await lock(recoveryLockPath, {
      lockfilePath: recoveryLockPath,
      realpath: false,
      stale: 30_000,
      update: 10_000,
      retries: {
        retries: 20,
        minTimeout: 10,
        maxTimeout: 50,
        randomize: true
      }
    })
  } catch (error) {
    const code = error instanceof Error && 'code' in error ? error.code : undefined
    if (code === 'ELOCKED') throw targetBusyError(rootDir, slug)
    throw error
  }

  const maxRaceRecoveryAttempts = 5
  try {
    for (let attempt = 0; attempt < maxRaceRecoveryAttempts; attempt++) {
      try {
        return await lock(lockPath, {
          lockfilePath: lockPath,
          realpath: false,
          stale: 10_000,
          update: 3_000,
          retries: 0
        })
      } catch (error) {
        const code = error instanceof Error && 'code' in error ? error.code : undefined
        if (code === 'ELOCKED') throw targetBusyError(rootDir, slug)
        if (
          (code === 'ENOENT' || code === 'EPERM' || code === 'EACCES')
          && attempt < maxRaceRecoveryAttempts - 1
        ) {
          await new Promise(resolve => setTimeout(resolve, 10 * (attempt + 1)))
          continue
        }
        throw error
      }
    }
    throw targetBusyError(rootDir, slug)
  } finally {
    await releaseRecoveryLock()
  }
}

export async function skillTargetLockPath(rootDir: string, slug: string): Promise<string> {
  const canonicalRoot = await canonicalizeExistingPath(resolve(rootDir))
  const target = resolve(canonicalRoot, slug)
  const digest = createHash('sha256').update(target).digest('hex')
  const uid = typeof process.getuid === 'function' ? process.getuid() : 'user'
  const lockDir = join(tmpdir(), `skillhub-cli-target-locks-${uid}`)
  await ensurePrivateLockDir(lockDir)
  return join(lockDir, `${digest}.lock`)
}

interface LockDirectoryDetails {
  isDirectory(): boolean
  isSymbolicLink(): boolean
  uid: number
  mode: number
}

export function assertPrivateLockDir(
  lockDir: string,
  details: LockDirectoryDetails,
  currentUid: number | null
): void {
  if (!details.isDirectory() || details.isSymbolicLink()) {
    throw new Error(`unsafe SkillHub CLI lock directory: ${lockDir}`)
  }
  if (currentUid !== null && details.uid !== currentUid) {
    throw new Error(`SkillHub CLI lock directory is owned by another user: ${lockDir}`)
  }
}

export async function ensurePrivateLockDir(lockDir: string): Promise<void> {
  try {
    await mkdir(lockDir, { mode: 0o700 })
  } catch (error) {
    if (!(error instanceof Error && 'code' in error && error.code === 'EEXIST')) throw error
  }

  const details = await lstat(lockDir)
  const currentUid = typeof process.getuid === 'function' ? process.getuid() : null
  assertPrivateLockDir(lockDir, details, currentUid)
  if (process.platform !== 'win32' && (details.mode & 0o077) !== 0) {
    await chmod(lockDir, 0o700)
  }
}

function targetBusyError(rootDir: string, slug: string): CliError {
  return new CliError(`install target is busy: ${join(rootDir, slug)}`, EXIT.filesystem, {
    path: join(rootDir, slug),
    next: 'wait for the other SkillHub CLI process to finish and retry'
  })
}

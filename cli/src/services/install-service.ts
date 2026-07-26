import { mkdir, mkdtemp, rename, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { SkillHubClient } from '../clients/skillhub-client'
import { InventoryStore } from '../stores/inventory-store'
import { CliError } from '../shared/errors'
import { EXIT } from '../shared/constants'
import { extractZip } from '../platform/archive'
import { readBoundedResponseBody } from '../platform/download'
import { canonicalizePath, pathExists } from '../platform/paths'
import type { AgentCandidate } from '../agents/types'

export interface InstallOptions {
  registry: string
  token?: string | undefined
  namespace: string
  slug: string
  version?: string | undefined
  targets: AgentCandidate[]
  force: boolean
  home?: string | undefined
}

function validateInstallSlug(slug: string): void {
  if (
    slug.length === 0 ||
    slug === '.' ||
    slug === '..' ||
    slug.includes('/') ||
    slug.includes('\\') ||
    slug.includes('\0')
  ) {
    throw new CliError('skill slug must be a single path segment', EXIT.usage, {
      slug,
      next: 'use the registry skill slug without path separators'
    })
  }
}

async function preflightInstallTargets(
  targets: AgentCandidate[],
  slug: string,
  force: boolean
): Promise<Array<{ target: AgentCandidate; skillDir: string }>> {
  validateInstallSlug(slug)
  const seenSkillDirs = new Set<string>()
  const preparedTargets: Array<{ target: AgentCandidate; skillDir: string }> = []

  for (const target of targets) {
    const canonicalRootDir = await canonicalizePath(target.rootDir)
    const canonicalSkillDir = join(canonicalRootDir, slug)
    const canonicalIdentity = process.platform === 'win32'
      ? canonicalSkillDir.toLowerCase()
      : canonicalSkillDir
    if (seenSkillDirs.has(canonicalIdentity)) {
      throw new CliError(`multiple install targets resolve to ${canonicalSkillDir}`, EXIT.usage, {
        path: canonicalSkillDir,
        next: 'select only one target for this directory'
      })
    }
    seenSkillDirs.add(canonicalIdentity)

    const skillDir = join(target.rootDir, slug)
    if (await pathExists(skillDir) && !force) {
      throw new CliError(`skill already installed at ${skillDir}`, EXIT.filesystem, {
        path: skillDir,
        next: 'pass --force to overwrite'
      })
    }
    preparedTargets.push({ target, skillDir })
  }

  return preparedTargets
}

export async function installSkill(options: InstallOptions): Promise<{ installed: Array<{ agent: string; dir: string }> }> {
  const preparedTargets = await preflightInstallTargets(options.targets, options.slug, options.force)
  const client = new SkillHubClient(options.registry, options.token)
  const resolved = await client.resolve(options.namespace, options.slug, options.version)
  const response = await client.download(options.namespace, options.slug, resolved.version)
  const buffer = await readBoundedResponseBody(response)

  const store = new InventoryStore(options.home)
  const stagedTargets: Array<{
    target: AgentCandidate
    skillDir: string
    tempDir: string
    installedAt: string
    movedIntoPlace: boolean
    backupDir: string | null
  }> = []
  let completed = false

  try {
    for (const { target, skillDir } of preparedTargets) {
      await mkdir(target.rootDir, { recursive: true })
      const tempDir = await mkdtemp(join(target.rootDir, `.${options.slug}.install-`))
      const installedAt = new Date().toISOString()
      const stagedTarget = {
        target,
        skillDir,
        tempDir,
        installedAt,
        movedIntoPlace: false,
        backupDir: null
      }
      stagedTargets.push(stagedTarget)

      await extractZip(buffer, tempDir)

      const metaDir = join(tempDir, '.skillhub')
      await mkdir(metaDir, { recursive: true })
      await writeFile(join(metaDir, 'metadata.json'), JSON.stringify({
        registry: options.registry,
        namespace: options.namespace,
        slug: options.slug,
        version: resolved.version,
        agent: target.agent,
        installedAt
      }, null, 2))
    }

    const previousInventory = await store.read()
    let inventoryChanged = false

    try {
      for (const stagedTarget of stagedTargets) {
        const { target, skillDir, tempDir } = stagedTarget

        if (await pathExists(skillDir) && !options.force) {
          throw new CliError(`skill already installed at ${skillDir}`, EXIT.filesystem, {
            path: skillDir,
            next: 'pass --force to overwrite'
          })
        }

        if (await pathExists(skillDir) && options.force) {
          stagedTarget.backupDir = await mkdtemp(join(target.rootDir, `.${options.slug}.backup-`))
          await rm(stagedTarget.backupDir, { recursive: true, force: true })
          await rename(skillDir, stagedTarget.backupDir)
        }

        try {
          await rename(tempDir, skillDir)
        } catch (error) {
          if (!options.force && await pathExists(skillDir)) {
            throw new CliError(`skill already installed at ${skillDir}`, EXIT.filesystem, {
              path: skillDir,
              next: 'pass --force to overwrite'
            })
          }
          throw error
        }
        stagedTarget.movedIntoPlace = true
      }

      for (const { target, skillDir, installedAt } of stagedTargets) {
        inventoryChanged = true
        await store.removeTargetsByInstallDir(skillDir)
        await store.upsertTarget(options.registry, options.namespace, options.slug, resolved.version, {
          agent: target.agent,
          rootDir: target.rootDir,
          installDir: skillDir,
          installedAt
        })
      }
    } catch (error) {
      const rollbackErrors: unknown[] = []

      if (inventoryChanged) {
        try {
          await store.writeAtomic(previousInventory)
        } catch (rollbackError) {
          rollbackErrors.push(rollbackError)
        }
      }

      for (const stagedTarget of [...stagedTargets].reverse()) {
        if (stagedTarget.movedIntoPlace) {
          try {
            await rm(stagedTarget.skillDir, { recursive: true, force: true })
            stagedTarget.movedIntoPlace = false
          } catch (rollbackError) {
            rollbackErrors.push(rollbackError)
          }
        }
        if (stagedTarget.backupDir && !(await pathExists(stagedTarget.skillDir))) {
          try {
            await rename(stagedTarget.backupDir, stagedTarget.skillDir)
            stagedTarget.backupDir = null
          } catch (rollbackError) {
            rollbackErrors.push(rollbackError)
          }
        }
      }

      if (rollbackErrors.length > 0) {
        throw new AggregateError([error, ...rollbackErrors], 'installation failed and rollback was incomplete')
      }
      throw error
    }

    completed = true
    return {
      installed: stagedTargets.map(({ target, skillDir }) => ({ agent: target.agent, dir: skillDir }))
    }
  } finally {
    for (const stagedTarget of stagedTargets) {
      if (!stagedTarget.movedIntoPlace) {
        await rm(stagedTarget.tempDir, { recursive: true, force: true }).catch(() => {})
      }
      if (completed && stagedTarget.backupDir) {
        await rm(stagedTarget.backupDir, { recursive: true, force: true }).catch(() => {})
      }
    }
  }
}

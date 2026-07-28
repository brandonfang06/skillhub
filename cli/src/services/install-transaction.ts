import {
  mkdir,
  mkdtemp,
  rename as renamePath,
  rm,
  writeFile
} from 'node:fs/promises'
import { join } from 'node:path'
import type { AgentCandidate } from '../agents/types'
import { extractZip } from '../platform/archive'
import { canonicalizePath, pathExists } from '../platform/paths'
import { EXIT } from '../shared/constants'
import { CliError } from '../shared/errors'
import {
  applyInstalledCollection,
  applyInstalledTarget,
  InventoryStore,
  type InventoryCollection,
  type InventoryCollectionMember,
  type NormalizedInventory
} from '../stores/inventory-store'

export interface CollectionInstallCoordinate {
  namespace: string
  slug: string
  version: string
}

export interface LoadedInstallPackage {
  version: string
  archive: ArrayBuffer
}

export interface InstallPackagePlan {
  namespace: string
  slug: string
  collection?: CollectionInstallCoordinate | undefined
  load(): Promise<LoadedInstallPackage>
}

export interface InstallCollectionRecord {
  namespace: string
  slug: string
  version: string
  members: InventoryCollectionMember[]
}

export interface InstallPackagesOptions {
  registry: string
  packages: InstallPackagePlan[]
  targets: AgentCandidate[]
  force: boolean
  home?: string | undefined
  collection?: InstallCollectionRecord | undefined
}

export interface InstalledPackageTarget {
  namespace: string
  slug: string
  version: string
  agent: string
  dir: string
}

export interface InstallPackagesResult {
  installed: InstalledPackageTarget[]
}

type RenameOperation = (from: string, to: string) => Promise<void>

export interface InstallTransactionDeps {
  extractZip?: typeof extractZip
  rename?: RenameOperation
  canonicalizePath?: typeof canonicalizePath
  pathExists?: typeof pathExists
  pathIdentity?: (path: string) => string
  now?: () => string
  inventoryStore?: InventoryStore
}

interface PreparedDestination {
  packageIndex: number
  target: AgentCandidate
  skillDir: string
  canonicalIdentity: string
}

interface StagedDestination extends PreparedDestination {
  version: string
  tempDir: string
  installedAt: string
  movedIntoPlace: boolean
  backupDir: string | null
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

function defaultPathIdentity(path: string): string {
  return process.platform === 'win32' ? path.toLowerCase() : path
}

function cloneInventory(inventory: NormalizedInventory): NormalizedInventory {
  return {
    items: inventory.items.map(item => ({
      ...item,
      targets: item.targets.map(target => ({ ...target }))
    })),
    collections: inventory.collections.map(collection => ({
      ...collection,
      members: collection.members.map(member => ({ ...member }))
    }))
  }
}

async function removeInventoryDestinations(
  inventory: NormalizedInventory,
  destinationIdentities: Set<string>,
  canonicalize: typeof canonicalizePath,
  identity: (path: string) => string
): Promise<NormalizedInventory> {
  const next = cloneInventory(inventory)
  for (const item of next.items) {
    const retained = []
    for (const target of item.targets) {
      const targetIdentity = identity(await canonicalize(target.installDir))
      if (!destinationIdentities.has(targetIdentity)) {
        retained.push(target)
      }
    }
    item.targets = retained
  }
  next.items = next.items.filter(item => item.targets.length > 0)
  return next
}

export async function installPackages(
  options: InstallPackagesOptions,
  deps: InstallTransactionDeps = {}
): Promise<InstallPackagesResult> {
  if (options.packages.length === 0 || options.targets.length === 0) {
    throw new CliError('installation requires packages and targets', EXIT.usage)
  }

  const canonicalize = deps.canonicalizePath ?? canonicalizePath
  const exists = deps.pathExists ?? pathExists
  const identity = deps.pathIdentity ?? defaultPathIdentity
  const extract = deps.extractZip ?? extractZip
  const rename: RenameOperation = deps.rename ?? (
    async (from, to) => renamePath(from, to)
  )
  const now = deps.now ?? (() => new Date().toISOString())
  const prepared: PreparedDestination[] = []
  const seenDestinations = new Set<string>()

  for (const [packageIndex, packagePlan] of options.packages.entries()) {
    validateInstallSlug(packagePlan.slug)
    for (const target of options.targets) {
      const canonicalRoot = await canonicalize(target.rootDir)
      const canonicalSkillDir = join(canonicalRoot, packagePlan.slug)
      const canonicalIdentity = identity(canonicalSkillDir)
      if (seenDestinations.has(canonicalIdentity)) {
        throw new CliError(
          `multiple install targets resolve to ${canonicalSkillDir}`,
          EXIT.usage,
          {
            path: canonicalSkillDir,
            next: 'select only one package and target for this directory'
          }
        )
      }
      seenDestinations.add(canonicalIdentity)

      const skillDir = join(target.rootDir, packagePlan.slug)
      if (await exists(skillDir) && !options.force) {
        throw new CliError(
          `skill already installed at ${skillDir}`,
          EXIT.filesystem,
          {
            path: skillDir,
            next: 'pass --force to overwrite'
          }
        )
      }
      prepared.push({
        packageIndex,
        target,
        skillDir,
        canonicalIdentity
      })
    }
  }

  const staged: StagedDestination[] = []
  const store = deps.inventoryStore ?? new InventoryStore(options.home)
  let completed = false
  let inventoryWriteStarted = false
  let previousInventory: NormalizedInventory | null = null
  let inventoryExisted = false

  try {
    for (const [packageIndex, packagePlan] of options.packages.entries()) {
      const loadedPackage = await packagePlan.load()
      if (!loadedPackage.version.trim()) {
        throw new CliError('resolved skill version is invalid', EXIT.generic)
      }
      for (const destination of prepared) {
        if (destination.packageIndex !== packageIndex) continue
        await mkdir(destination.target.rootDir, { recursive: true })
        const tempDir = await mkdtemp(
          join(destination.target.rootDir, `.${packagePlan.slug}.install-`)
        )
        const installedAt = now()
        const stagedDestination: StagedDestination = {
          ...destination,
          version: loadedPackage.version,
          tempDir,
          installedAt,
          movedIntoPlace: false,
          backupDir: null
        }
        staged.push(stagedDestination)

        await extract(loadedPackage.archive, tempDir)
        const metadataDir = join(tempDir, '.skillhub')
        await mkdir(metadataDir, { recursive: true })
        await writeFile(
          join(metadataDir, 'metadata.json'),
          JSON.stringify({
            registry: options.registry,
            namespace: packagePlan.namespace,
            slug: packagePlan.slug,
            version: loadedPackage.version,
            agent: destination.target.agent,
            installedAt,
            ...(packagePlan.collection
              ? { collection: packagePlan.collection }
              : {})
          }, null, 2)
        )
      }
    }

    inventoryExisted = await exists(store.path)
    previousInventory = await store.read()
    let nextInventory = await removeInventoryDestinations(
      previousInventory,
      new Set(prepared.map(destination => destination.canonicalIdentity)),
      canonicalize,
      identity
    )

    for (const destination of staged) {
      const packagePlan = options.packages[destination.packageIndex]!
      nextInventory = applyInstalledTarget(
        nextInventory,
        {
          registry: options.registry,
          namespace: packagePlan.namespace,
          slug: packagePlan.slug,
          version: destination.version
        },
        {
          agent: destination.target.agent,
          rootDir: destination.target.rootDir,
          installDir: destination.skillDir,
          installedAt: destination.installedAt
        }
      )
    }

    if (options.collection) {
      const collection: InventoryCollection = {
        registry: options.registry,
        namespace: options.collection.namespace,
        slug: options.collection.slug,
        version: options.collection.version,
        members: options.collection.members.map(member => ({ ...member })),
        installedAt: now()
      }
      nextInventory = applyInstalledCollection(nextInventory, collection)
    }

    for (const destination of staged) {
      if (await exists(destination.skillDir) && !options.force) {
        throw new CliError(
          `skill already installed at ${destination.skillDir}`,
          EXIT.filesystem,
          {
            path: destination.skillDir,
            next: 'pass --force to overwrite'
          }
        )
      }

      if (await exists(destination.skillDir) && options.force) {
        const backupDir = await mkdtemp(
          join(destination.target.rootDir, `.${options.packages[destination.packageIndex]!.slug}.backup-`)
        )
        await rm(backupDir, { recursive: true, force: true })
        await rename(destination.skillDir, backupDir)
        destination.backupDir = backupDir
      }

      try {
        await rename(destination.tempDir, destination.skillDir)
      } catch (error) {
        if (!options.force && await exists(destination.skillDir)) {
          throw new CliError(
            `skill already installed at ${destination.skillDir}`,
            EXIT.filesystem,
            {
              path: destination.skillDir,
              next: 'pass --force to overwrite'
            }
          )
        }
        throw error
      }
      destination.movedIntoPlace = true
    }

    inventoryWriteStarted = true
    await store.writeAtomic(nextInventory)
    completed = true
    return {
      installed: staged.map(destination => {
        const packagePlan = options.packages[destination.packageIndex]!
        return {
          namespace: packagePlan.namespace,
          slug: packagePlan.slug,
          version: destination.version,
          agent: destination.target.agent,
          dir: destination.skillDir
        }
      })
    }
  } catch (error) {
    const rollbackErrors: unknown[] = []

    if (inventoryWriteStarted && previousInventory) {
      try {
        if (inventoryExisted) {
          await store.writeAtomic(previousInventory)
        } else {
          await rm(store.path, { force: true })
        }
      } catch (rollbackError) {
        rollbackErrors.push(rollbackError)
      }
    }

    for (const destination of [...staged].reverse()) {
      if (destination.movedIntoPlace) {
        try {
          await rm(destination.skillDir, { recursive: true, force: true })
          destination.movedIntoPlace = false
        } catch (rollbackError) {
          rollbackErrors.push(rollbackError)
        }
      }
      if (destination.backupDir && !(await exists(destination.skillDir))) {
        try {
          await rename(destination.backupDir, destination.skillDir)
          destination.backupDir = null
        } catch (rollbackError) {
          rollbackErrors.push(rollbackError)
        }
      }
    }

    if (rollbackErrors.length > 0) {
      throw new AggregateError(
        [error, ...rollbackErrors],
        'installation failed and rollback was incomplete'
      )
    }
    throw error
  } finally {
    for (const destination of staged) {
      if (!destination.movedIntoPlace) {
        await rm(destination.tempDir, { recursive: true, force: true }).catch(
          () => {}
        )
      }
      if (completed && destination.backupDir) {
        await rm(destination.backupDir, { recursive: true, force: true }).catch(
          () => {}
        )
      }
    }
  }
}

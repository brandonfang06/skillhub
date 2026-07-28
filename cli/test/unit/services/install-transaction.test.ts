import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  rename,
  rm,
  writeFile
} from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, test } from 'bun:test'
import { zipSync } from 'fflate'
import {
  installPackages,
  type InstallPackagePlan
} from '../../../src/services/install-transaction'
import { InventoryStore } from '../../../src/stores/inventory-store'

const cleanupPaths: string[] = []

async function tempDir(prefix: string): Promise<string> {
  const path = await mkdtemp(join(tmpdir(), prefix))
  cleanupPaths.push(path)
  return path
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

function archive(entries: Record<string, string>): ArrayBuffer {
  const zipped = zipSync(Object.fromEntries(
    Object.entries(entries).map(([name, value]) => [
      name,
      new TextEncoder().encode(value)
    ])
  ))
  return zipped.buffer.slice(
    zipped.byteOffset,
    zipped.byteOffset + zipped.byteLength
  ) as ArrayBuffer
}

function packagePlan(
  slug: string,
  version: string,
  loadArchive: () => Promise<ArrayBuffer>
): InstallPackagePlan {
  return {
    namespace: 'opensource',
    slug,
    load: async () => ({
      version,
      archive: await loadArchive()
    })
  }
}

afterEach(async () => {
  for (const path of cleanupPaths.splice(0).reverse()) {
    await rm(path, { recursive: true, force: true })
  }
})

describe('installPackages', () => {
  test('preflights every package destination before the first download', async () => {
    const home = await tempDir('skillhub-transaction-home-')
    const rootDir = await tempDir('skillhub-transaction-root-')
    await mkdir(join(rootDir, 'second'))
    let loadCalls = 0

    await expect(installPackages({
      registry: 'https://skillhub.example.test',
      packages: [
        packagePlan('first', '1.0.0', async () => {
          loadCalls += 1
          return archive({ 'SKILL.md': '# First' })
        }),
        packagePlan('second', '2.0.0', async () => {
          loadCalls += 1
          return archive({ 'SKILL.md': '# Second' })
        })
      ],
      targets: [{
        agent: 'codex',
        rootDir,
        scope: 'project',
        source: 'explicit'
      }],
      force: false,
      home
    })).rejects.toThrow(`skill already installed at ${join(rootDir, 'second')}`)

    expect(loadCalls).toBe(0)
    expect(await exists(join(rootDir, 'first'))).toBe(false)
    expect(await exists(join(home, '.skillhub', 'inventory.json'))).toBe(false)
  })

  test('a later download failure leaves destinations and inventory unchanged', async () => {
    const home = await tempDir('skillhub-transaction-home-')
    const rootDir = await tempDir('skillhub-transaction-root-')
    const inventoryPath = join(home, '.skillhub', 'inventory.json')
    await mkdir(join(home, '.skillhub'), { recursive: true })
    await writeFile(inventoryPath, JSON.stringify({
      items: [],
      collections: []
    }))

    await expect(installPackages({
      registry: 'https://skillhub.example.test',
      packages: [
        packagePlan('first', '1.0.0', async () => archive({
          'SKILL.md': '# First'
        })),
        packagePlan('second', '2.0.0', async () => {
          throw new Error('second download failed')
        })
      ],
      targets: [{
        agent: 'codex',
        rootDir,
        scope: 'project',
        source: 'explicit'
      }],
      force: false,
      home
    })).rejects.toThrow('second download failed')

    expect(await exists(join(rootDir, 'first'))).toBe(false)
    expect(await exists(join(rootDir, 'second'))).toBe(false)
    expect(JSON.parse(await readFile(inventoryPath, 'utf-8'))).toEqual({
      items: [],
      collections: []
    })
  })

  test('loads and extracts one package at a time before inventory write', async () => {
    const home = await tempDir('skillhub-transaction-home-')
    const rootDir = await tempDir('skillhub-transaction-root-')
    const events: string[] = []
    const store = new InventoryStore(home)
    const writeAtomic = store.writeAtomic.bind(store)
    store.writeAtomic = async (inventory) => {
      events.push('inventory:write')
      await writeAtomic(inventory)
    }

    await installPackages({
      registry: 'https://skillhub.example.test',
      packages: [
        packagePlan('first', '1.0.0', async () => {
          events.push('load:first')
          return archive({ 'SKILL.md': '# First' })
        }),
        packagePlan('second', '2.0.0', async () => {
          events.push('load:second')
          return archive({ 'SKILL.md': '# Second' })
        })
      ],
      targets: [{
        agent: 'codex',
        rootDir,
        scope: 'project',
        source: 'explicit'
      }],
      force: false,
      home
    }, {
      extractZip: async (buffer, dir) => {
        events.push(`extract:${dir.includes('first') ? 'first' : 'second'}`)
        const { extractZip } = await import('../../../src/platform/archive')
        await extractZip(buffer, dir)
      },
      rename: async (from, to) => {
        events.push(`rename:${to.endsWith('first') ? 'first' : 'second'}`)
        await rename(from, to)
      },
      inventoryStore: store
    })

    expect(events.filter(event =>
      event.startsWith('load:') ||
      event.startsWith('extract:') ||
      event === 'inventory:write'
    )).toEqual([
      'load:first',
      'extract:first',
      'load:second',
      'extract:second',
      'inventory:write'
    ])
  })

  test('a later rename failure removes earlier installs and preserves inventory', async () => {
    const home = await tempDir('skillhub-transaction-home-')
    const rootDir = await tempDir('skillhub-transaction-root-')
    const inventoryPath = join(home, '.skillhub', 'inventory.json')
    const previousInventory = {
      items: [],
      collections: []
    }
    await mkdir(join(home, '.skillhub'), { recursive: true })
    await writeFile(inventoryPath, JSON.stringify(previousInventory))
    let commitRenames = 0

    await expect(installPackages({
      registry: 'https://skillhub.example.test',
      packages: [
        packagePlan('first', '1.0.0', async () => archive({
          'SKILL.md': '# First'
        })),
        packagePlan('second', '2.0.0', async () => archive({
          'SKILL.md': '# Second'
        }))
      ],
      targets: [{
        agent: 'codex',
        rootDir,
        scope: 'project',
        source: 'explicit'
      }],
      force: false,
      home
    }, {
      rename: async (from, to) => {
        if (!to.includes('.backup-')) {
          commitRenames += 1
          if (commitRenames === 2) {
            throw new Error('second rename failed')
          }
        }
        await rename(from, to)
      }
    })).rejects.toThrow('second rename failed')

    expect(await exists(join(rootDir, 'first'))).toBe(false)
    expect(await exists(join(rootDir, 'second'))).toBe(false)
    expect(JSON.parse(await readFile(inventoryPath, 'utf-8'))).toEqual(
      previousInventory
    )
  })

  test('force restores every original directory when a later commit fails', async () => {
    const home = await tempDir('skillhub-transaction-home-')
    const rootDir = await tempDir('skillhub-transaction-root-')
    await mkdir(join(rootDir, 'first'))
    await mkdir(join(rootDir, 'second'))
    await writeFile(join(rootDir, 'first', 'old.txt'), 'old first')
    await writeFile(join(rootDir, 'second', 'old.txt'), 'old second')
    let renameCalls = 0

    await expect(installPackages({
      registry: 'https://skillhub.example.test',
      packages: [
        packagePlan('first', '1.0.0', async () => archive({
          'SKILL.md': '# New First'
        })),
        packagePlan('second', '2.0.0', async () => archive({
          'SKILL.md': '# New Second'
        }))
      ],
      targets: [{
        agent: 'codex',
        rootDir,
        scope: 'project',
        source: 'explicit'
      }],
      force: true,
      home
    }, {
      rename: async (from, to) => {
        renameCalls += 1
        if (renameCalls === 4) {
          throw new Error('second forced commit failed')
        }
        await rename(from, to)
      }
    })).rejects.toThrow('second forced commit failed')

    expect(await readFile(join(rootDir, 'first', 'old.txt'), 'utf-8')).toBe(
      'old first'
    )
    expect(await readFile(join(rootDir, 'second', 'old.txt'), 'utf-8')).toBe(
      'old second'
    )
    expect(await exists(join(rootDir, 'first', 'SKILL.md'))).toBe(false)
    expect(await exists(join(rootDir, 'second', 'SKILL.md'))).toBe(false)
  })

  test('restores destinations and the prior inventory after an inventory write failure', async () => {
    const home = await tempDir('skillhub-transaction-home-')
    const rootDir = await tempDir('skillhub-transaction-root-')
    const store = new InventoryStore(home)
    const previousInventory = {
      items: [{
        registry: 'https://skillhub.example.test',
        namespace: 'opensource',
        slug: 'existing',
        version: '1.0.0',
        targets: []
      }],
      collections: []
    }
    await store.writeAtomic(previousInventory)
    const writeAtomic = store.writeAtomic.bind(store)
    let writeCalls = 0
    store.writeAtomic = async (inventory) => {
      writeCalls += 1
      await writeAtomic(inventory)
      if (writeCalls === 1) {
        throw new Error('inventory write failed after replace')
      }
    }

    await expect(installPackages({
      registry: 'https://skillhub.example.test',
      packages: [
        packagePlan('first', '1.0.0', async () => archive({
          'SKILL.md': '# First'
        }))
      ],
      targets: [{
        agent: 'codex',
        rootDir,
        scope: 'project',
        source: 'explicit'
      }],
      force: false,
      home
    }, {
      inventoryStore: store
    })).rejects.toThrow('inventory write failed after replace')

    expect(writeCalls).toBe(2)
    expect(await exists(join(rootDir, 'first'))).toBe(false)
    expect(await store.read()).toEqual(previousInventory)
  })

  test('rejects case-only duplicate destinations with an injected Windows identity', async () => {
    const home = await tempDir('skillhub-transaction-home-')
    const parent = await tempDir('skillhub-transaction-root-')
    let loadCalls = 0

    await expect(installPackages({
      registry: 'https://skillhub.example.test',
      packages: [
        packagePlan('demo', '1.0.0', async () => {
          loadCalls += 1
          return archive({ 'SKILL.md': '# Demo' })
        })
      ],
      targets: [
        {
          agent: 'codex',
          rootDir: join(parent, 'Skills'),
          scope: 'project',
          source: 'explicit'
        },
        {
          agent: 'generic',
          rootDir: join(parent, 'skills'),
          scope: 'project',
          source: 'explicit'
        }
      ],
      force: false,
      home
    }, {
      pathIdentity: path => path.toLowerCase()
    })).rejects.toThrow('multiple install targets resolve to')

    expect(loadCalls).toBe(0)
  })

  test('writes exact collection metadata and one inventory snapshot', async () => {
    const home = await tempDir('skillhub-transaction-home-')
    const rootDir = await tempDir('skillhub-transaction-root-')

    const result = await installPackages({
      registry: 'https://skillhub.example.test',
      packages: [{
        ...packagePlan('brainstorming', '4.1.0', async () => archive({
          'SKILL.md': '# Brainstorming'
        })),
        collection: {
          namespace: 'opensource',
          slug: 'superpowers',
          version: '1.2.0'
        }
      }],
      collection: {
        namespace: 'opensource',
        slug: 'superpowers',
        version: '1.2.0',
        members: [{
          namespace: 'opensource',
          slug: 'brainstorming',
          version: '4.1.0'
        }]
      },
      targets: [{
        agent: 'codex',
        rootDir,
        scope: 'project',
        source: 'explicit'
      }],
      force: false,
      home
    })

    const metadata = JSON.parse(await readFile(
      join(rootDir, 'brainstorming', '.skillhub', 'metadata.json'),
      'utf-8'
    ))
    expect(metadata).toMatchObject({
      registry: 'https://skillhub.example.test',
      namespace: 'opensource',
      slug: 'brainstorming',
      version: '4.1.0',
      agent: 'codex',
      collection: {
        namespace: 'opensource',
        slug: 'superpowers',
        version: '1.2.0'
      }
    })

    const inventory = JSON.parse(await readFile(
      join(home, '.skillhub', 'inventory.json'),
      'utf-8'
    ))
    expect(inventory.items).toHaveLength(1)
    expect(inventory.collections).toEqual([expect.objectContaining({
      namespace: 'opensource',
      slug: 'superpowers',
      version: '1.2.0'
    })])
    expect(result.installed).toEqual([expect.objectContaining({
      namespace: 'opensource',
      slug: 'brainstorming',
      version: '4.1.0',
      agent: 'codex',
      dir: join(rootDir, 'brainstorming')
    })])
  })
})

import { describe, expect, test } from 'bun:test'
import { mkdir, writeFile } from 'node:fs/promises'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { InventoryStore } from '../../../src/stores/inventory-store'

function makeTempHome() {
  return mkdtemp(join(tmpdir(), 'skillhub-store-test-'))
}

function makeTarget(slug: string) {
  return {
    agent: 'claude',
    rootDir: `/projects/${slug}`,
    installDir: `/projects/${slug}/.skillhub/skills/${slug}`,
    installedAt: new Date().toISOString(),
  }
}

describe('InventoryStore', () => {
  test('normalizes an absent inventory to empty items and collections', async () => {
    const home = await makeTempHome()
    const store = new InventoryStore(home)

    expect(await store.read()).toEqual({
      items: [],
      collections: []
    })
  })

  test('normalizes a legacy inventory without collections', async () => {
    const home = await makeTempHome()
    const store = new InventoryStore(home)
    await mkdir(dirname(store.path), { recursive: true })
    await writeFile(store.path, JSON.stringify({ items: [] }))

    expect(await store.read()).toEqual({
      items: [],
      collections: []
    })
  })

  test('preserves collections while single-skill inventory methods run', async () => {
    const home = await makeTempHome()
    const store = new InventoryStore(home)
    await store.writeAtomic({
      items: [],
      collections: [{
        registry: 'https://skillhub.example.test',
        namespace: 'opensource',
        slug: 'superpowers',
        version: '1.2.0',
        members: [{
          namespace: 'opensource',
          slug: 'brainstorming',
          version: '4.1.0'
        }],
        installedAt: '2026-07-27T00:00:00.000Z'
      }]
    })

    await store.upsertTarget(
      'https://skillhub.example.test',
      'opensource',
      'brainstorming',
      '4.1.0',
      makeTarget('brainstorming')
    )

    const inventory = await store.read()
    expect(inventory.collections).toHaveLength(1)
    expect(inventory.collections[0]?.slug).toBe('superpowers')
  })

  test('5 sequential upsertTarget calls all persist', async () => {
    const home = await makeTempHome()
    const store = new InventoryStore(home)

    for (let i = 0; i < 5; i++) {
      await store.upsertTarget(
        'https://skill.xfyun.cn',
        'global',
        `skill-${i}`,
        '1.0.0',
        makeTarget(`skill-${i}`),
      )
    }

    const inventory = await store.read()
    expect(inventory.items).toHaveLength(5)
  })

  test('recovers from stale lock file', async () => {
    const home = await makeTempHome()
    const store = new InventoryStore(home)

    // Ensure the directory for the lock file exists
    await mkdir(dirname(store.path), { recursive: true })

    // Write a stale lock: dead PID + old timestamp
    const lockPath = `${store.path}.lock`
    await writeFile(
      lockPath,
      JSON.stringify({ pid: 999999, timestamp: Date.now() - 60000 }),
    )

    // upsertTarget should recover from the stale lock and succeed
    await store.upsertTarget(
      'https://skill.xfyun.cn',
      'global',
      'test-skill',
      '1.0.0',
      makeTarget('test-skill'),
    )

    const inventory = await store.read()
    expect(inventory.items).toHaveLength(1)
    expect(inventory.items[0]?.slug).toBe('test-skill')
  })

  test('removeTarget returns false when item not found', async () => {
    const home = await makeTempHome()
    const store = new InventoryStore(home)

    const result = await store.removeTarget(
      'https://skill.xfyun.cn',
      'global',
      'nonexistent',
      '/some/path',
    )
    expect(result).toBe(false)
  })

  test('removeTargetsByInstallDir returns 0 when no matches', async () => {
    const home = await makeTempHome()
    const store = new InventoryStore(home)

    // Seed one item so the inventory file exists
    await store.upsertTarget(
      'https://skill.xfyun.cn',
      'global',
      'existing-skill',
      '1.0.0',
      makeTarget('existing-skill'),
    )

    const removed = await store.removeTargetsByInstallDir('/nonexistent/path')
    expect(removed).toBe(0)

    // Original item should still be there
    const inventory = await store.read()
    expect(inventory.items).toHaveLength(1)
  })
})

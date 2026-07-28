import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, test } from 'bun:test'
import { strToU8, zipSync } from 'fflate'
import { createTempHome } from '../helpers/temp-env'
import { startFakeRegistry } from '../helpers/fake-registry'
import { runCli } from '../helpers/run-cli'

function makeSkillZip(title: string): Uint8Array {
  return zipSync({
    'SKILL.md': strToU8(`# ${title}`)
  })
}

function collectionFixture() {
  return {
    namespace: 'opensource',
    slug: 'superpowers',
    version: '1.2.0',
    versionId: 120,
    members: [
      {
        namespace: 'opensource',
        slug: 'brainstorming',
        version: '4.1.0',
        versionId: 901,
        fingerprint: `sha256:${'a'.repeat(64)}`
      },
      {
        namespace: 'opensource',
        slug: 'verification',
        version: '2.0.0',
        versionId: 902,
        fingerprint: `sha256:${'b'.repeat(64)}`
      }
    ]
  }
}

let registry: Awaited<ReturnType<typeof startFakeRegistry>> | undefined

afterEach(() => {
  registry?.stop()
  registry = undefined
})

describe('collection install command', () => {
  test('installs the exact ordered snapshot and records collection metadata', async () => {
    const env = await createTempHome()
    registry = await startFakeRegistry({
      token: 'sk_ok',
      collections: [collectionFixture()],
      skills: [
        {
          namespace: 'opensource',
          slug: 'brainstorming',
          version: '4.1.0',
          zipBytes: makeSkillZip('Brainstorming')
        },
        {
          namespace: 'opensource',
          slug: 'verification',
          version: '2.0.0',
          zipBytes: makeSkillZip('Verification')
        }
      ]
    })
    const installRoot = join(env.cwd, 'skills')

    const result = await runCli([
      'collection', 'install', '@opensource/superpowers',
      '--version', '1.2.0',
      '--dir', installRoot,
      '--registry', registry.url,
      '--token', 'sk_ok',
      '--json'
    ], {
      HOME: env.home,
      USERPROFILE: env.home
    }, {
      cwd: env.cwd
    })

    expect(result.exitCode).toBe(0)
    const output = JSON.parse(result.stdout)
    expect(output).toMatchObject({
      ok: true,
      collection: {
        namespace: 'opensource',
        slug: 'superpowers',
        version: '1.2.0'
      }
    })
    expect(output.members.map((member: { slug: string }) => member.slug)).toEqual([
      'brainstorming',
      'verification'
    ])

    for (const [slug, version] of [
      ['brainstorming', '4.1.0'],
      ['verification', '2.0.0']
    ] as const) {
      const metadata = JSON.parse(await readFile(
        join(installRoot, slug, '.skillhub', 'metadata.json'),
        'utf-8'
      ))
      expect(metadata).toMatchObject({
        namespace: 'opensource',
        slug,
        version,
        collection: {
          namespace: 'opensource',
          slug: 'superpowers',
          version: '1.2.0'
        }
      })
    }

    const inventory = JSON.parse(await readFile(
      join(env.home, '.skillhub', 'inventory.json'),
      'utf-8'
    ))
    expect(inventory.items).toHaveLength(2)
    expect(inventory.collections).toEqual([expect.objectContaining({
      namespace: 'opensource',
      slug: 'superpowers',
      version: '1.2.0'
    })])
    expect(registry.received.collectionResolve).toMatchObject({
      namespace: 'opensource',
      slug: 'superpowers',
      version: '1.2.0',
      token: 'Bearer sk_ok'
    })
  })

  test('a later destination conflict prevents every member download', async () => {
    const env = await createTempHome()
    registry = await startFakeRegistry({
      collections: [collectionFixture()],
      skills: [
        {
          namespace: 'opensource',
          slug: 'brainstorming',
          version: '4.1.0',
          zipBytes: makeSkillZip('Brainstorming')
        },
        {
          namespace: 'opensource',
          slug: 'verification',
          version: '2.0.0',
          zipBytes: makeSkillZip('Verification')
        }
      ]
    })
    const installRoot = join(env.cwd, 'skills')
    await mkdir(join(installRoot, 'verification'), { recursive: true })
    await writeFile(join(installRoot, 'verification', 'old.txt'), 'keep')

    const result = await runCli([
      'collection', 'install', '@opensource/superpowers',
      '--dir', installRoot,
      '--registry', registry.url
    ], {
      HOME: env.home,
      USERPROFILE: env.home
    }, {
      cwd: env.cwd
    })

    expect(result.exitCode).not.toBe(0)
    expect(registry.received.downloads).toEqual([])
    expect(await Bun.file(join(installRoot, 'brainstorming')).exists()).toBe(false)
    expect(await readFile(
      join(installRoot, 'verification', 'old.txt'),
      'utf-8'
    )).toBe('keep')
  })

  test('a later download failure preserves every forced destination', async () => {
    const env = await createTempHome()
    registry = await startFakeRegistry({
      collections: [collectionFixture()],
      skills: [
        {
          namespace: 'opensource',
          slug: 'brainstorming',
          version: '4.1.0',
          zipBytes: makeSkillZip('Brainstorming')
        },
        {
          namespace: 'opensource',
          slug: 'verification',
          version: '2.0.0',
          zipBytes: makeSkillZip('Verification')
        }
      ],
      downloadFailures: {
        'opensource/verification': 'server_error'
      }
    })
    const installRoot = join(env.cwd, 'skills')
    for (const slug of ['brainstorming', 'verification']) {
      await mkdir(join(installRoot, slug), { recursive: true })
      await writeFile(join(installRoot, slug, 'old.txt'), `old ${slug}`)
    }

    const result = await runCli([
      'collection', 'install', '@opensource/superpowers',
      '--dir', installRoot,
      '--registry', registry.url,
      '--force'
    ], {
      HOME: env.home,
      USERPROFILE: env.home
    }, {
      cwd: env.cwd
    })

    expect(result.exitCode).not.toBe(0)
    expect(await readFile(
      join(installRoot, 'brainstorming', 'old.txt'),
      'utf-8'
    )).toBe('old brainstorming')
    expect(await readFile(
      join(installRoot, 'verification', 'old.txt'),
      'utf-8'
    )).toBe('old verification')
  })

  test('rejects an unsafe server member before any download', async () => {
    const env = await createTempHome()
    const unsafe = collectionFixture()
    unsafe.members[1]!.slug = '../escape'
    registry = await startFakeRegistry({
      collections: [unsafe],
      skills: []
    })

    const result = await runCli([
      'collection', 'install', '@opensource/superpowers',
      '--dir', join(env.cwd, 'skills'),
      '--registry', registry.url
    ], {
      HOME: env.home,
      USERPROFILE: env.home
    }, {
      cwd: env.cwd
    })

    expect(result.exitCode).not.toBe(0)
    expect(result.stderr).toContain('invalid collection manifest')
    expect(registry.received.downloads).toEqual([])
    expect(await Bun.file(join(env.cwd, 'escape')).exists()).toBe(false)
  })

  test('normalizes a legacy inventory while adding the collection record', async () => {
    const env = await createTempHome()
    registry = await startFakeRegistry({
      collections: [collectionFixture()],
      skills: [
        {
          namespace: 'opensource',
          slug: 'brainstorming',
          version: '4.1.0',
          zipBytes: makeSkillZip('Brainstorming')
        },
        {
          namespace: 'opensource',
          slug: 'verification',
          version: '2.0.0',
          zipBytes: makeSkillZip('Verification')
        }
      ]
    })
    const inventoryPath = join(env.home, '.skillhub', 'inventory.json')
    await mkdir(join(env.home, '.skillhub'), { recursive: true })
    await writeFile(inventoryPath, JSON.stringify({ items: [] }))

    const result = await runCli([
      'collection', 'install', '@opensource/superpowers',
      '--dir', join(env.cwd, 'skills'),
      '--registry', registry.url,
      '--json'
    ], {
      HOME: env.home,
      USERPROFILE: env.home
    }, {
      cwd: env.cwd
    })

    expect(result.exitCode).toBe(0)
    const inventory = JSON.parse(await readFile(inventoryPath, 'utf-8'))
    expect(inventory.collections).toHaveLength(1)
  })

  test('legacy install, list, remove, and doctor preserve collection records', async () => {
    const env = await createTempHome()
    registry = await startFakeRegistry({
      collections: [collectionFixture()],
      skills: [
        {
          namespace: 'opensource',
          slug: 'brainstorming',
          version: '4.1.0',
          zipBytes: makeSkillZip('Brainstorming')
        },
        {
          namespace: 'opensource',
          slug: 'verification',
          version: '2.0.0',
          zipBytes: makeSkillZip('Verification')
        },
        {
          namespace: 'global',
          slug: 'standalone',
          version: '1.0.0',
          zipBytes: makeSkillZip('Standalone')
        }
      ]
    })
    const installRoot = join(env.cwd, '.codex', 'skills')
    const processEnv = {
      HOME: env.home,
      USERPROFILE: env.home
    }

    const collection = await runCli([
      'collection', 'install', '@opensource/superpowers',
      '--dir', installRoot,
      '--registry', registry.url
    ], processEnv, {
      cwd: env.cwd
    })
    expect(collection.exitCode).toBe(0)

    const standalone = await runCli([
      'install', 'standalone',
      '--dir', installRoot,
      '--registry', registry.url
    ], processEnv, {
      cwd: env.cwd
    })
    expect(standalone.exitCode).toBe(0)

    const list = await runCli([
      'list',
      '--registry', registry.url,
      '--json'
    ], processEnv, {
      cwd: env.cwd
    })
    expect(JSON.parse(list.stdout).items).toHaveLength(3)

    const remove = await runCli([
      'remove', 'standalone',
      '--all',
      '--registry', registry.url
    ], processEnv, {
      cwd: env.cwd
    })
    expect(remove.exitCode).toBe(0)

    const doctor = await runCli(['doctor', '--json'], processEnv, {
      cwd: env.cwd
    })
    expect(doctor.exitCode).toBe(0)

    const inventory = JSON.parse(await readFile(
      join(env.home, '.skillhub', 'inventory.json'),
      'utf-8'
    ))
    expect(inventory.items.map((item: { slug: string }) => item.slug).sort())
      .toEqual(['brainstorming', 'verification'])
    expect(inventory.collections).toEqual([expect.objectContaining({
      namespace: 'opensource',
      slug: 'superpowers',
      version: '1.2.0'
    })])
  })
})

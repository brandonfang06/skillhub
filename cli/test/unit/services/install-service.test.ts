import { access, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, test } from 'bun:test'
import { zipSync } from 'fflate'
import { installSkill } from '../../../src/services/install-service'

const originalFetch = globalThis.fetch

async function exists(path: string): Promise<boolean> {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

function installFetch(zipEntries: Record<string, string>): typeof fetch {
  const archive = zipSync(Object.fromEntries(
    Object.entries(zipEntries).map(([name, content]) => [name, new TextEncoder().encode(content)])
  ))

  return installFetchWithDownloadResponse(new Response(
    archive.buffer.slice(archive.byteOffset, archive.byteOffset + archive.byteLength) as ArrayBuffer,
    { status: 200 }
  ))
}

function installFetchWithDownloadResponse(downloadResponse: Response): typeof fetch {
  const fakeFetch = async (input: URL | RequestInfo) => {
    const path = new URL(String(input)).pathname
    if (path.endsWith('/resolve')) {
      return Response.json({
        code: 0,
        data: {
          namespace: 'global',
          slug: 'demo',
          version: '1.0.0',
          versionId: 1,
          fingerprint: 'fp',
          downloadUrl: '/download'
        }
      })
    }
    if (path.endsWith('/download')) {
      return downloadResponse.clone()
    }
    return Response.json({ code: 404 }, { status: 404 })
  }
  return fakeFetch as unknown as typeof fetch
}

function countingFetch(delegate: typeof fetch, onCall: () => void): typeof fetch {
  return ((input: URL | RequestInfo, init?: RequestInit) => {
    onCall()
    return delegate(input, init)
  }) as typeof fetch
}

describe('installSkill', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  test('fails when target skill directory already exists without metadata', async () => {
    globalThis.fetch = installFetch({ 'SKILL.md': '# Demo' })
    const rootDir = await mkdtemp(join(tmpdir(), 'skillhub-install-root-'))
    const skillDir = join(rootDir, 'demo')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'local.txt'), 'keep')

    await expect(installSkill({
      registry: 'http://registry.test',
      namespace: 'global',
      slug: 'demo',
      targets: [{ agent: 'codex', rootDir, scope: 'project', source: 'explicit' }],
      force: false
    })).rejects.toThrow('skill already installed')
  })

  test('preflights all targets before network or writes when a later target is occupied', async () => {
    let fetchCalls = 0
    globalThis.fetch = countingFetch(installFetch({ 'SKILL.md': '# Demo' }), () => fetchCalls++)
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const firstRoot = await mkdtemp(join(tmpdir(), 'skillhub-install-first-root-'))
    const secondRoot = await mkdtemp(join(tmpdir(), 'skillhub-install-second-root-'))
    const firstSkillDir = join(firstRoot, 'demo')
    const secondSkillDir = join(secondRoot, 'demo')
    await mkdir(secondSkillDir, { recursive: true })

    try {
      await expect(installSkill({
        registry: 'http://registry.test',
        namespace: 'global',
        slug: 'demo',
        targets: [
          { agent: 'codex', rootDir: firstRoot, scope: 'project', source: 'explicit' },
          { agent: 'claude-code', rootDir: secondRoot, scope: 'project', source: 'explicit' }
        ],
        force: false,
        home
      })).rejects.toThrow(`skill already installed at ${secondSkillDir}`)

      expect(fetchCalls).toBe(0)
      expect(await exists(firstSkillDir)).toBe(false)
      expect(await exists(join(home, '.skillhub', 'inventory.json'))).toBe(false)
    } finally {
      await rm(home, { recursive: true, force: true })
      await rm(firstRoot, { recursive: true, force: true })
      await rm(secondRoot, { recursive: true, force: true })
    }
  })

  test('rolls back earlier targets when a later conflict appears after download', async () => {
    const delegate = installFetch({ 'SKILL.md': '# Demo' })
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const firstRoot = await mkdtemp(join(tmpdir(), 'skillhub-install-first-root-'))
    const secondRoot = await mkdtemp(join(tmpdir(), 'skillhub-install-second-root-'))
    const firstSkillDir = join(firstRoot, 'demo')
    const secondSkillDir = join(secondRoot, 'demo')
    const inventoryPath = join(home, '.skillhub', 'inventory.json')

    globalThis.fetch = (async (input: URL | RequestInfo, init?: RequestInit) => {
      if (new URL(String(input)).pathname.endsWith('/download')) {
        await mkdir(secondSkillDir)
        await writeFile(join(secondSkillDir, 'local.txt'), 'keep')
      }
      return delegate(input, init)
    }) as typeof fetch

    try {
      await expect(installSkill({
        registry: 'http://registry.test',
        namespace: 'global',
        slug: 'demo',
        targets: [
          { agent: 'codex', rootDir: firstRoot, scope: 'project', source: 'explicit' },
          { agent: 'claude-code', rootDir: secondRoot, scope: 'project', source: 'explicit' }
        ],
        force: false,
        home
      })).rejects.toThrow(`skill already installed at ${secondSkillDir}`)

      expect(await exists(firstSkillDir)).toBe(false)
      expect(await readFile(join(secondSkillDir, 'local.txt'), 'utf-8')).toBe('keep')
      if (await exists(inventoryPath)) {
        expect(JSON.parse(await readFile(inventoryPath, 'utf-8')).items).toEqual([])
      }
    } finally {
      await rm(home, { recursive: true, force: true })
      await rm(firstRoot, { recursive: true, force: true })
      await rm(secondRoot, { recursive: true, force: true })
    }
  })

  test('rejects unsafe slug path segments before network or writes', async () => {
    let fetchCalls = 0
    globalThis.fetch = countingFetch(installFetch({ 'SKILL.md': '# Demo' }), () => fetchCalls++)
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const targetParent = await mkdtemp(join(tmpdir(), 'skillhub-install-targets-'))
    const rootDir = join(targetParent, 'skills')
    await mkdir(rootDir)

    try {
      for (const slug of ['', '.', '..', '../outside', 'nested/skill', 'nested\\skill', 'nul\0skill']) {
        await expect(installSkill({
          registry: 'http://registry.test',
          namespace: 'global',
          slug,
          targets: [{ agent: 'custom', rootDir, scope: 'user', source: 'explicit' }],
          force: true,
          home
        })).rejects.toThrow('skill slug must be a single path segment')
      }

      expect(fetchCalls).toBe(0)
      expect(await exists(join(targetParent, 'outside'))).toBe(false)
      expect(await exists(join(home, '.skillhub', 'inventory.json'))).toBe(false)
    } finally {
      await rm(home, { recursive: true, force: true })
      await rm(targetParent, { recursive: true, force: true })
    }
  })

  test('rejects canonical target aliases before network or writes', async () => {
    let fetchCalls = 0
    globalThis.fetch = countingFetch(installFetch({ 'SKILL.md': '# Demo' }), () => fetchCalls++)
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const targetParent = await mkdtemp(join(tmpdir(), 'skillhub-install-targets-'))
    const genericRoot = join(targetParent, 'generic')
    const codexRoot = join(targetParent, 'codex')
    const skillDir = join(genericRoot, 'demo')

    try {
      await mkdir(genericRoot, { recursive: true })
      await symlink(genericRoot, codexRoot, process.platform === 'win32' ? 'junction' : 'dir')

      await expect(installSkill({
        registry: 'http://registry.test',
        namespace: 'global',
        slug: 'demo',
        targets: [
          { agent: 'codex', rootDir: codexRoot, scope: 'user', source: 'detected' },
          { agent: 'generic', rootDir: genericRoot, scope: 'user', source: 'fallback' }
        ],
        force: false,
        home
      })).rejects.toThrow('multiple install targets resolve to')

      expect(fetchCalls).toBe(0)
      expect(await exists(skillDir)).toBe(false)
      expect(await exists(join(home, '.skillhub', 'inventory.json'))).toBe(false)
    } finally {
      await rm(home, { recursive: true, force: true })
      await rm(targetParent, { recursive: true, force: true })
    }
  })

  test('rejects missing target roots beneath canonical parent aliases before network or writes', async () => {
    let fetchCalls = 0
    globalThis.fetch = countingFetch(installFetch({ 'SKILL.md': '# Demo' }), () => fetchCalls++)
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const targetParent = await mkdtemp(join(tmpdir(), 'skillhub-install-targets-'))
    const realParent = join(targetParent, 'real-parent')
    const aliasParent = join(targetParent, 'alias-parent')
    const realRoot = join(realParent, 'missing', 'skills')
    const aliasRoot = join(aliasParent, 'missing', 'skills')
    const skillDir = join(realRoot, 'demo')

    try {
      await mkdir(realParent, { recursive: true })
      await symlink(realParent, aliasParent, process.platform === 'win32' ? 'junction' : 'dir')

      await expect(installSkill({
        registry: 'http://registry.test',
        namespace: 'global',
        slug: 'demo',
        targets: [
          { agent: 'codex', rootDir: aliasRoot, scope: 'user', source: 'detected' },
          { agent: 'generic', rootDir: realRoot, scope: 'user', source: 'fallback' }
        ],
        force: false,
        home
      })).rejects.toThrow('multiple install targets resolve to')

      expect(fetchCalls).toBe(0)
      expect(await exists(skillDir)).toBe(false)
      expect(await exists(join(home, '.skillhub', 'inventory.json'))).toBe(false)
    } finally {
      await rm(home, { recursive: true, force: true })
      await rm(targetParent, { recursive: true, force: true })
    }
  })

  test('rejects missing target roots that differ only by case on Windows', async () => {
    if (process.platform !== 'win32') return

    let fetchCalls = 0
    globalThis.fetch = countingFetch(installFetch({ 'SKILL.md': '# Demo' }), () => fetchCalls++)
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const targetParent = await mkdtemp(join(tmpdir(), 'skillhub-install-targets-'))
    const upperRoot = join(targetParent, 'Missing', 'Skills')
    const lowerRoot = join(targetParent, 'missing', 'skills')

    try {
      await expect(installSkill({
        registry: 'http://registry.test',
        namespace: 'global',
        slug: 'demo',
        targets: [
          { agent: 'codex', rootDir: upperRoot, scope: 'user', source: 'detected' },
          { agent: 'generic', rootDir: lowerRoot, scope: 'user', source: 'fallback' }
        ],
        force: false,
        home
      })).rejects.toThrow('multiple install targets resolve to')

      expect(fetchCalls).toBe(0)
      expect(await exists(join(upperRoot, 'demo'))).toBe(false)
      expect(await exists(join(home, '.skillhub', 'inventory.json'))).toBe(false)
    } finally {
      await rm(home, { recursive: true, force: true })
      await rm(targetParent, { recursive: true, force: true })
    }
  })

  test('force replaces the old skill directory instead of overlaying files', async () => {
    globalThis.fetch = installFetch({ 'SKILL.md': '# New' })
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const rootDir = await mkdtemp(join(tmpdir(), 'skillhub-install-root-'))
    const skillDir = join(rootDir, 'demo')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'stale.txt'), 'old')

    await installSkill({
      registry: 'http://registry.test',
      namespace: 'global',
      slug: 'demo',
      targets: [{ agent: 'codex', rootDir, scope: 'project', source: 'explicit' }],
      force: true,
      home
    })

    expect(await readFile(join(skillDir, 'SKILL.md'), 'utf-8')).toBe('# New')
    expect(await exists(join(skillDir, 'stale.txt'))).toBe(false)
  })

  test('force removes stale inventory records that point at the replaced install directory', async () => {
    globalThis.fetch = installFetch({ 'SKILL.md': '# Team Demo' })
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const rootDir = await mkdtemp(join(tmpdir(), 'skillhub-install-root-'))
    const skillDir = join(rootDir, 'demo')
    await mkdir(skillDir, { recursive: true })
    const inventoryPath = join(home, '.skillhub', 'inventory.json')
    await mkdir(join(home, '.skillhub'), { recursive: true })
    await writeFile(inventoryPath, JSON.stringify({
      items: [{
        registry: 'http://registry.test',
        namespace: 'global',
        slug: 'demo',
        version: '0.1.0',
        targets: [{
          agent: 'codex',
          rootDir,
          installDir: skillDir,
          installedAt: '2026-04-20T00:00:00.000Z'
        }]
      }]
    }))

    await installSkill({
      registry: 'http://registry.test',
      namespace: 'team',
      slug: 'demo',
      targets: [{ agent: 'codex', rootDir, scope: 'project', source: 'explicit' }],
      force: true,
      home
    })

    const inventory = JSON.parse(await readFile(inventoryPath, 'utf-8'))
    expect(inventory.items).toHaveLength(1)
    expect(inventory.items[0]).toMatchObject({ namespace: 'team', slug: 'demo' })
    expect(inventory.items[0].targets).toHaveLength(1)
    expect(inventory.items[0].targets[0].installDir).toBe(skillDir)
  })

  test('force removes stale inventory records written through a canonical path alias', async () => {
    globalThis.fetch = installFetch({ 'SKILL.md': '# Team Demo' })
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const targetParent = await mkdtemp(join(tmpdir(), 'skillhub-install-targets-'))
    const realRoot = join(targetParent, 'real')
    const aliasRoot = join(targetParent, 'alias')
    const realSkillDir = join(realRoot, 'demo')
    const aliasSkillDir = join(aliasRoot, 'demo')
    const inventoryPath = join(home, '.skillhub', 'inventory.json')

    try {
      await mkdir(realSkillDir, { recursive: true })
      await writeFile(join(realSkillDir, 'SKILL.md'), '# Old')
      await symlink(realRoot, aliasRoot, process.platform === 'win32' ? 'junction' : 'dir')
      await mkdir(join(home, '.skillhub'), { recursive: true })
      await writeFile(inventoryPath, JSON.stringify({
        items: [{
          registry: 'http://registry.test',
          namespace: 'global',
          slug: 'demo',
          version: '0.1.0',
          targets: [{
            agent: 'codex',
            rootDir: realRoot,
            installDir: realSkillDir,
            installedAt: '2026-04-20T00:00:00.000Z'
          }]
        }]
      }))

      await installSkill({
        registry: 'http://registry.test',
        namespace: 'team',
        slug: 'demo',
        targets: [{ agent: 'custom', rootDir: aliasRoot, scope: 'user', source: 'explicit' }],
        force: true,
        home
      })

      const inventory = JSON.parse(await readFile(inventoryPath, 'utf-8'))
      expect(inventory.items).toHaveLength(1)
      expect(inventory.items[0]).toMatchObject({ namespace: 'team', slug: 'demo' })
      expect(inventory.items[0].targets).toHaveLength(1)
      expect(inventory.items[0].targets[0].installDir).toBe(aliasSkillDir)
    } finally {
      await rm(home, { recursive: true, force: true })
      await rm(targetParent, { recursive: true, force: true })
    }
  })

  test('force keeps old installation and inventory when replacement extraction fails', async () => {
    globalThis.fetch = installFetchWithDownloadResponse(new Response(new TextEncoder().encode('not a zip'), { status: 200 }))
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const rootDir = await mkdtemp(join(tmpdir(), 'skillhub-install-root-'))
    const skillDir = join(rootDir, 'demo')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '# Old')
    const inventoryPath = join(home, '.skillhub', 'inventory.json')
    await mkdir(join(home, '.skillhub'), { recursive: true })
    await writeFile(inventoryPath, JSON.stringify({
      items: [{
        registry: 'http://registry.test',
        namespace: 'global',
        slug: 'demo',
        version: '0.1.0',
        targets: [{
          agent: 'codex',
          rootDir,
          installDir: skillDir,
          installedAt: '2026-04-20T00:00:00.000Z'
        }]
      }]
    }, null, 2))

    await expect(installSkill({
      registry: 'http://registry.test',
      namespace: 'global',
      slug: 'demo',
      targets: [{ agent: 'codex', rootDir, scope: 'project', source: 'explicit' }],
      force: true,
      home
    })).rejects.toThrow('invalid zip central directory')

    expect(await readFile(join(skillDir, 'SKILL.md'), 'utf-8')).toBe('# Old')
    const inventory = JSON.parse(await readFile(inventoryPath, 'utf-8'))
    expect(inventory.items).toHaveLength(1)
    expect(inventory.items[0]).toMatchObject({ namespace: 'global', slug: 'demo', version: '0.1.0' })
    expect(inventory.items[0].targets[0].installDir).toBe(skillDir)
  })

  test('rejects downloads whose content-length exceeds the package limit', async () => {
    globalThis.fetch = installFetchWithDownloadResponse(new Response(new Uint8Array(0), {
      status: 200,
      headers: { 'Content-Length': String(100 * 1024 * 1024 + 1) }
    }))
    const rootDir = await mkdtemp(join(tmpdir(), 'skillhub-install-root-'))

    await expect(installSkill({
      registry: 'http://registry.test',
      namespace: 'global',
      slug: 'demo',
      targets: [{ agent: 'codex', rootDir, scope: 'project', source: 'explicit' }],
      force: false
    })).rejects.toThrow('download exceeds maximum package size')
  })

  test('verifies a supplied manifest fingerprint before replacing an existing skill', async () => {
    globalThis.fetch = installFetch({ 'SKILL.md': '# New' })
    const home = await mkdtemp(join(tmpdir(), 'skillhub-install-home-'))
    const rootDir = await mkdtemp(join(tmpdir(), 'skillhub-install-root-'))
    const skillDir = join(rootDir, 'demo')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '# Old')

    try {
      await expect(installSkill({
        registry: 'http://registry.test',
        namespace: 'global',
        slug: 'demo',
        resolved: {
          namespace: 'global',
          slug: 'demo',
          version: '1.0.0',
          versionId: 1,
          fingerprint: 'sha256:not-the-downloaded-snapshot',
          downloadUrl: '/download'
        },
        verifyFingerprint: true,
        targets: [{ agent: 'workspace', rootDir, scope: 'project', source: 'explicit' }],
        force: true,
        home
      })).rejects.toThrow('downloaded skill fingerprint does not match namespace manifest')

      expect(await readFile(join(skillDir, 'SKILL.md'), 'utf-8')).toBe('# Old')
      expect(await exists(join(skillDir, '.skillhub', 'metadata.json'))).toBe(false)
    } finally {
      await rm(home, { recursive: true, force: true })
      await rm(rootDir, { recursive: true, force: true })
    }
  })
})

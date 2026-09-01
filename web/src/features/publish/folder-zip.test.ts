import { describe, expect, it } from 'vitest'
import {
  FolderPackagingError,
  collectFolderEntries,
  createZipBlob,
  crc32,
  isIgnoredPath,
  normalizeArchivePath,
  packageFolderAsZip,
} from './folder-zip'

const utf8 = new TextEncoder()

function fileAt(relativePath: string, content = 'x'): File {
  const name = relativePath.replace(/\\/g, '/').split('/').pop() || relativePath
  const file = new File([content], name)
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath })
  return file
}

async function bytesOf(blob: Blob): Promise<Uint8Array> {
  return new Uint8Array(await blob.arrayBuffer())
}

async function expectPackagingError(
  promise: Promise<unknown>,
  code: FolderPackagingError['code'],
) {
  await expect(promise).rejects.toMatchObject({ code })
}

describe('normalizeArchivePath', () => {
  it('normalizes Windows separators without changing safe relative paths', () => {
    expect(normalizeArchivePath('my-skill\\scripts\\run.ps1')).toBe(
      'my-skill/scripts/run.ps1',
    )
    expect(normalizeArchivePath('my-skill/SKILL.md')).toBe('my-skill/SKILL.md')
  })

  it.each([
    '',
    '/absolute/SKILL.md',
    'C:/skill/SKILL.md',
    'my-skill/../secret.txt',
    'my-skill/./SKILL.md',
    'my-skill//SKILL.md',
    'my-skill/SKILL.md\0hidden',
  ])('rejects unsafe archive path %j', (path) => {
    expect(() => normalizeArchivePath(path)).toThrowError(
      expect.objectContaining({ code: 'unsafe-path' }),
    )
  })
})

describe('isIgnoredPath', () => {
  it('keeps normal skill files', () => {
    expect(isIgnoredPath('my-skill/SKILL.md')).toBe(false)
    expect(isIgnoredPath('my-skill/scripts/run.sh')).toBe(false)
  })

  it('drops local metadata, VCS, build, cache, and OS junk', () => {
    expect(isIgnoredPath('my-skill/.skillhub/sync-workspace.json')).toBe(true)
    expect(isIgnoredPath('my-skill/.git/config')).toBe(true)
    expect(isIgnoredPath('my-skill/node_modules/x/index.js')).toBe(true)
    expect(isIgnoredPath('my-skill/__pycache__/m.pyc')).toBe(true)
    expect(isIgnoredPath('my-skill/.DS_Store')).toBe(true)
    expect(isIgnoredPath('my-skill/._resource')).toBe(true)
    expect(isIgnoredPath('my-skill/Thumbs.db')).toBe(true)
  })
})

describe('crc32', () => {
  it('matches known CRC-32/ISO-HDLC vectors', () => {
    expect(crc32(utf8.encode(''))).toBe(0x00000000)
    expect(crc32(utf8.encode('a'))).toBe(0xe8b7be43)
    expect(crc32(utf8.encode('abc'))).toBe(0x352441c2)
  })
})

describe('createZipBlob', () => {
  it('writes a STORE archive with local, central, and EOCD records', async () => {
    const blob = createZipBlob([{ path: 'SKILL.md', data: utf8.encode('hello') }])
    const bytes = await bytesOf(blob)
    const view = new DataView(bytes.buffer)

    expect(view.getUint32(0, true)).toBe(0x04034b50)
    const eocd = bytes.length - 22
    expect(view.getUint32(eocd, true)).toBe(0x06054b50)
    expect(view.getUint16(eocd + 10, true)).toBe(1)
    const centralDirectoryOffset = view.getUint32(eocd + 16, true)
    expect(view.getUint32(centralDirectoryOffset, true)).toBe(0x02014b50)
  })

  it('rejects duplicate normalized paths', () => {
    expect(() => createZipBlob([
      { path: 'skill\\SKILL.md', data: utf8.encode('one') },
      { path: 'skill/SKILL.md', data: utf8.encode('two') },
    ])).toThrowError(expect.objectContaining({ code: 'duplicate-path' }))
  })
})

describe('collectFolderEntries', () => {
  it('filters junk, normalizes separators, and sorts remaining files by path', async () => {
    const entries = await collectFolderEntries([
      fileAt('my-skill\\scripts\\run.sh', 'run'),
      fileAt('my-skill/.git/config', 'gitcfg'),
      fileAt('my-skill/.skillhub/inventory.json', 'local state'),
      fileAt('my-skill/SKILL.md', 'md'),
    ])

    expect(entries.map((entry) => entry.path)).toEqual([
      'my-skill/SKILL.md',
      'my-skill/scripts/run.sh',
    ])
  })

  it('rejects duplicate paths after normalization', async () => {
    await expectPackagingError(collectFolderEntries([
      fileAt('my-skill\\SKILL.md', 'one'),
      fileAt('my-skill/SKILL.md', 'two'),
    ]), 'duplicate-path')
  })

  it('enforces file-count, per-file, and total-size limits before packaging', async () => {
    await expectPackagingError(
      collectFolderEntries(
        [fileAt('skill/SKILL.md'), fileAt('skill/README.md')],
        { maxFiles: 1, maxFileBytes: 10, maxTotalBytes: 1000 },
      ),
      'too-many-files',
    )
    await expectPackagingError(
      collectFolderEntries(
        [fileAt('skill/SKILL.md', 'abc')],
        { maxFiles: 2, maxFileBytes: 2, maxTotalBytes: 1000 },
      ),
      'file-too-large',
    )
    await expectPackagingError(
      collectFolderEntries(
        [fileAt('skill/SKILL.md', 'ab'), fileAt('skill/README.md', 'cd')],
        { maxFiles: 2, maxFileBytes: 3, maxTotalBytes: 200 },
      ),
      'package-too-large',
    )
  })
})

describe('packageFolderAsZip', () => {
  it('names the zip after the normalized top-level folder', async () => {
    const file = await packageFolderAsZip([fileAt('my-skill\\SKILL.md', 'md')])

    expect(file.name).toBe('my-skill.zip')
    expect(file.type).toBe('application/zip')
    expect(file.size).toBeGreaterThan(0)
  })

  it('throws when every selected file is filtered out', async () => {
    await expectPackagingError(
      packageFolderAsZip([fileAt('my-skill/.git/config', 'x')]),
      'empty-folder',
    )
  })

  it('enforces the limit against final archive bytes including ZIP headers', async () => {
    const source = [fileAt('skill/SKILL.md', 'x')]

    await expectPackagingError(
      packageFolderAsZip(source, {
        maxFiles: 2,
        maxFileBytes: 10,
        maxTotalBytes: 126,
      }),
      'package-too-large',
    )

    const archive = await packageFolderAsZip(source, {
      maxFiles: 2,
      maxFileBytes: 10,
      maxTotalBytes: 127,
    })
    expect(archive.size).toBe(127)
  })
})

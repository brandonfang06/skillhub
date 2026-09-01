/** Directory names whose entire subtree is excluded from a browser-built package. */
const IGNORED_DIR_SEGMENTS = new Set([
  '.git',
  '.svn',
  '.hg',
  '.skillhub',
  'node_modules',
  '__pycache__',
  '__macosx',
])

/** Exact file names that are always excluded. */
const IGNORED_FILE_NAMES = new Set(['.ds_store', 'thumbs.db', 'desktop.ini'])

const MAX_ZIP_PATH_BYTES = 0xffff
const utf8 = new TextEncoder()

function comparePaths(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0
}

export interface FolderPackageLimits {
  maxFiles: number
  maxFileBytes: number
  maxTotalBytes: number
}

/** Mirrors the Python package boundary in server-python/app/publish/package.py. */
export const FOLDER_PACKAGE_LIMITS: Readonly<FolderPackageLimits> = Object.freeze({
  maxFiles: 500,
  maxFileBytes: 10 * 1024 * 1024,
  maxTotalBytes: 100 * 1024 * 1024,
})

export type FolderPackagingErrorCode =
  | 'empty-folder'
  | 'unsafe-path'
  | 'duplicate-path'
  | 'path-too-long'
  | 'too-many-files'
  | 'file-too-large'
  | 'package-too-large'

export class FolderPackagingError extends Error {
  readonly code: FolderPackagingErrorCode
  readonly path?: string
  readonly limit?: number
  readonly actual?: number

  constructor(
    code: FolderPackagingErrorCode,
    details: { path?: string; limit?: number; actual?: number } = {},
  ) {
    super(code)
    this.name = 'FolderPackagingError'
    this.code = code
    this.path = details.path
    this.limit = details.limit
    this.actual = details.actual
  }
}

export function normalizeArchivePath(relativePath: string): string {
  const normalized = relativePath.replace(/\\/g, '/')
  const segments = normalized.split('/')
  const hasUnsafeSegment = segments.some(
    (segment) => segment === '' || segment === '.' || segment === '..',
  )

  if (
    normalized.includes('\0')
    || normalized.startsWith('/')
    || /^[a-zA-Z]:\//.test(normalized)
    || hasUnsafeSegment
  ) {
    throw new FolderPackagingError('unsafe-path', { path: relativePath })
  }

  if (utf8.encode(normalized).length > MAX_ZIP_PATH_BYTES) {
    throw new FolderPackagingError('path-too-long', {
      path: normalized,
      limit: MAX_ZIP_PATH_BYTES,
    })
  }

  return normalized
}

/** Returns true if a normalized relative path should be excluded from the package. */
export function isIgnoredPath(relativePath: string): boolean {
  const parts = normalizeArchivePath(relativePath)
    .split('/')
    .map((part) => part.toLowerCase())
  const name = parts[parts.length - 1]

  if (!name) return true
  if (parts.some((segment) => IGNORED_DIR_SEGMENTS.has(segment))) return true
  if (IGNORED_FILE_NAMES.has(name)) return true
  if (name.startsWith('._')) return true
  return name.endsWith('.pyc') || name.endsWith('.swp')
}

// CRC-32/ISO-HDLC, polynomial 0xEDB88320.
const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let index = 0; index < table.length; index += 1) {
    let value = index
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1
    }
    table[index] = value >>> 0
  }
  return table
})()

export function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff
  for (const byte of bytes) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

export interface ZipEntry {
  path: string
  data: Uint8Array
}

/** Builds a deterministic STORE-method ZIP without adding a runtime dependency. */
export function createZipBlob(entries: ZipEntry[]): Blob {
  const normalizedEntries = entries
    .map((entry) => ({ ...entry, path: normalizeArchivePath(entry.path) }))
    .sort((left, right) => comparePaths(left.path, right.path))
  const seenPaths = new Set<string>()
  const localParts: Uint8Array[] = []
  const centralParts: Uint8Array[] = []
  let offset = 0

  for (const entry of normalizedEntries) {
    if (seenPaths.has(entry.path)) {
      throw new FolderPackagingError('duplicate-path', { path: entry.path })
    }
    seenPaths.add(entry.path)

    const nameBytes = utf8.encode(entry.path)
    const checksum = crc32(entry.data)
    const size = entry.data.length

    const local = new Uint8Array(30 + nameBytes.length)
    const localView = new DataView(local.buffer)
    localView.setUint32(0, 0x04034b50, true)
    localView.setUint16(4, 20, true)
    localView.setUint16(6, 0x0800, true)
    localView.setUint16(8, 0, true)
    localView.setUint16(10, 0, true)
    localView.setUint16(12, 0, true)
    localView.setUint32(14, checksum, true)
    localView.setUint32(18, size, true)
    localView.setUint32(22, size, true)
    localView.setUint16(26, nameBytes.length, true)
    localView.setUint16(28, 0, true)
    local.set(nameBytes, 30)
    localParts.push(local, entry.data)

    const central = new Uint8Array(46 + nameBytes.length)
    const centralView = new DataView(central.buffer)
    centralView.setUint32(0, 0x02014b50, true)
    centralView.setUint16(4, 20, true)
    centralView.setUint16(6, 20, true)
    centralView.setUint16(8, 0x0800, true)
    centralView.setUint16(10, 0, true)
    centralView.setUint16(12, 0, true)
    centralView.setUint16(14, 0, true)
    centralView.setUint32(16, checksum, true)
    centralView.setUint32(20, size, true)
    centralView.setUint32(24, size, true)
    centralView.setUint16(28, nameBytes.length, true)
    centralView.setUint16(30, 0, true)
    centralView.setUint16(32, 0, true)
    centralView.setUint16(34, 0, true)
    centralView.setUint16(36, 0, true)
    centralView.setUint32(38, 0, true)
    centralView.setUint32(42, offset, true)
    central.set(nameBytes, 46)
    centralParts.push(central)

    offset += local.length + entry.data.length
  }

  const centralSize = centralParts.reduce((total, part) => total + part.length, 0)
  const end = new Uint8Array(22)
  const endView = new DataView(end.buffer)
  endView.setUint32(0, 0x06054b50, true)
  endView.setUint16(4, 0, true)
  endView.setUint16(6, 0, true)
  endView.setUint16(8, normalizedEntries.length, true)
  endView.setUint16(10, normalizedEntries.length, true)
  endView.setUint32(12, centralSize, true)
  endView.setUint32(16, offset, true)
  endView.setUint16(20, 0, true)

  const parts = [...localParts, ...centralParts, end]
  const totalSize = parts.reduce((total, part) => total + part.length, 0)
  const output = new Uint8Array(totalSize)
  let position = 0
  for (const part of parts) {
    output.set(part, position)
    position += part.length
  }
  return new Blob([output], { type: 'application/zip' })
}

function relativePathOf(file: File): string {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
}

export async function collectFolderEntries(
  files: File[],
  limits: FolderPackageLimits = FOLDER_PACKAGE_LIMITS,
): Promise<ZipEntry[]> {
  const selected: Array<{ file: File; path: string }> = []
  const seenPaths = new Set<string>()
  let archiveBytes = 22

  for (const file of files) {
    const path = normalizeArchivePath(relativePathOf(file))
    if (isIgnoredPath(path)) continue

    if (seenPaths.has(path)) {
      throw new FolderPackagingError('duplicate-path', { path })
    }
    seenPaths.add(path)

    if (file.size > limits.maxFileBytes) {
      throw new FolderPackagingError('file-too-large', {
        path,
        limit: limits.maxFileBytes,
        actual: file.size,
      })
    }

    selected.push({ file, path })
    if (selected.length > limits.maxFiles) {
      throw new FolderPackagingError('too-many-files', {
        limit: limits.maxFiles,
        actual: selected.length,
      })
    }

    archiveBytes += file.size + 76 + (2 * utf8.encode(path).length)
    if (archiveBytes > limits.maxTotalBytes) {
      throw new FolderPackagingError('package-too-large', {
        limit: limits.maxTotalBytes,
        actual: archiveBytes,
      })
    }
  }

  selected.sort((left, right) => comparePaths(left.path, right.path))
  return Promise.all(selected.map(async ({ file, path }) => ({
    path,
    data: new Uint8Array(await file.arrayBuffer()),
  })))
}

function archiveName(entries: ZipEntry[]): string {
  const firstPath = entries[0]?.path
  if (!firstPath?.includes('/')) return 'skill.zip'
  return `${firstPath.slice(0, firstPath.indexOf('/'))}.zip`
}

export async function packageFolderAsZip(
  fileList: FileList | File[],
  limits: FolderPackageLimits = FOLDER_PACKAGE_LIMITS,
): Promise<File> {
  const entries = await collectFolderEntries(Array.from(fileList), limits)
  if (entries.length === 0) {
    throw new FolderPackagingError('empty-folder')
  }
  return new File([createZipBlob(entries)], archiveName(entries), {
    type: 'application/zip',
  })
}

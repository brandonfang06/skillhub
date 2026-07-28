import type { AgentCandidate } from '../agents/types'
import {
  SkillHubClient,
  type CollectionResolveResponse
} from '../clients/skillhub-client'
import { readBoundedResponseBody } from '../platform/download'
import { isSafeCollectionSegment } from '../shared/collection-name-parser'
import { EXIT, MAX_COLLECTION_MEMBERS } from '../shared/constants'
import { CliError } from '../shared/errors'
import {
  installPackages,
  type InstallPackagesOptions,
  type InstalledPackageTarget
} from './install-transaction'

export interface CollectionInstallOptions {
  registry: string
  token?: string | undefined
  namespace: string
  slug: string
  version?: string | undefined
  targets: AgentCandidate[]
  force: boolean
  home?: string | undefined
}

export interface CollectionInstallResult {
  collection: {
    namespace: string
    slug: string
    version: string
  }
  members: Array<{
    namespace: string
    slug: string
    version: string
  }>
  installed: InstalledPackageTarget[]
}

interface CollectionInstallDeps {
  client?: Pick<SkillHubClient, 'resolveCollection' | 'download'>
  installPackages?: (
    options: InstallPackagesOptions
  ) => Promise<{ installed: InstalledPackageTarget[] }>
}

function invalidManifest(reason: string): CliError {
  return new CliError('invalid collection manifest', EXIT.generic, { reason })
}

function validateManifest(
  requestedNamespace: string,
  requestedSlug: string,
  manifest: CollectionResolveResponse
): void {
  if (
    manifest.namespace !== requestedNamespace ||
    manifest.slug !== requestedSlug ||
    !isSafeCollectionSegment(manifest.namespace) ||
    !isSafeCollectionSegment(manifest.slug) ||
    !manifest.version.trim() ||
    manifest.members.length === 0 ||
    manifest.members.length > MAX_COLLECTION_MEMBERS
  ) {
    throw invalidManifest('collection coordinate or version is invalid')
  }

  const members = new Set<string>()
  for (const member of manifest.members) {
    if (
      member.namespace !== manifest.namespace ||
      !isSafeCollectionSegment(member.namespace) ||
      !isSafeCollectionSegment(member.slug) ||
      !member.version.trim()
    ) {
      throw invalidManifest('member coordinate or version is invalid')
    }
    const coordinate = `${member.namespace}/${member.slug}`
    if (members.has(coordinate)) {
      throw invalidManifest('member coordinate is duplicated')
    }
    members.add(coordinate)

    const expectedDownloadPath = (
      `/api/cli/v1/skills/${encodeURIComponent(member.namespace)}/` +
      `${encodeURIComponent(member.slug)}/versions/` +
      `${encodeURIComponent(member.version)}/download`
    )
    if (member.downloadUrl !== expectedDownloadPath) {
      throw invalidManifest('member download path does not match exact version')
    }
  }
}

export async function installCollection(
  options: CollectionInstallOptions,
  deps: CollectionInstallDeps = {}
): Promise<CollectionInstallResult> {
  const client = deps.client ?? new SkillHubClient(options.registry, options.token)
  const manifest = await client.resolveCollection(
    options.namespace,
    options.slug,
    options.version
  )
  validateManifest(options.namespace, options.slug, manifest)

  const collection = {
    namespace: manifest.namespace,
    slug: manifest.slug,
    version: manifest.version
  }
  const members = manifest.members.map(member => ({
    namespace: member.namespace,
    slug: member.slug,
    version: member.version
  }))
  const runTransaction = deps.installPackages ?? installPackages
  const result = await runTransaction({
    registry: options.registry,
    packages: manifest.members.map(member => ({
      namespace: member.namespace,
      slug: member.slug,
      collection,
      load: async () => {
        const response = await client.download(
          member.namespace,
          member.slug,
          member.version
        )
        return {
          version: member.version,
          archive: await readBoundedResponseBody(response)
        }
      }
    })),
    collection: {
      ...collection,
      members
    },
    targets: options.targets,
    force: options.force,
    home: options.home
  })

  return {
    collection,
    members,
    installed: result.installed
  }
}

import { resolveInstallTargets } from '../agents/resolver'
import type { AgentCandidate } from '../agents/types'
import { parseCollectionName } from '../shared/collection-name-parser'
import { EXIT } from '../shared/constants'
import { CliError } from '../shared/errors'
import { CredentialsStore } from '../stores/credentials-store'
import { resolveToken } from '../services/registry-service'
import {
  installCollection,
  type CollectionInstallOptions,
  type CollectionInstallResult
} from '../services/collection-install-service'
import {
  computeStrictIsTTY,
  promptInstallScope,
  resolveEffectiveScope
} from './install'

export interface CollectionCommandOptions {
  version?: string | undefined
  agent?: string[] | undefined
  dir?: string | undefined
  scope?: string | undefined
  force?: boolean | undefined
  registry?: string | undefined
  token?: string | undefined
  json?: boolean | undefined
}

export interface CollectionCommandDeps {
  promptScope?: () => Promise<'user' | 'project'>
  resolveInstallTargets?: typeof resolveInstallTargets
  installCollection?: (
    options: CollectionInstallOptions
  ) => Promise<CollectionInstallResult>
  isTTY?: () => boolean
  getStoredToken?: (registry: string) => Promise<string | undefined>
}

function normalizeRequiredRegistry(value: string | undefined): string {
  if (!value?.trim()) {
    throw new CliError(
      '--registry is required for collection install',
      EXIT.usage
    )
  }
  return value.trim().replace(/\/+$/, '')
}

function renderCollectionInstall(result: CollectionInstallResult): string {
  return [
    (
      `Installed collection @${result.collection.namespace}/` +
      `${result.collection.slug}@${result.collection.version}`
    ),
    ...result.installed.map(item =>
      `Installed ${item.namespace}/${item.slug}@${item.version} -> ` +
      `${item.dir} (${item.agent})`
    )
  ].join('\n')
}

export async function collectionInstallCommand(
  coordinate: string,
  options: CollectionCommandOptions,
  deps: CollectionCommandDeps = {}
): Promise<string> {
  const registry = normalizeRequiredRegistry(options.registry)
  const parsed = parseCollectionName(coordinate)
  const isTTY = (deps.isTTY ?? (() => computeStrictIsTTY({
    stdinIsTTY: process.stdin.isTTY === true,
    stdoutIsTTY: process.stdout.isTTY === true,
    json: Boolean(options.json)
  })))()
  const promptScope = deps.promptScope ?? promptInstallScope
  const effectiveScope = await resolveEffectiveScope(options, {
    isTTY,
    promptScope
  })

  const getStoredToken = deps.getStoredToken ?? (
    async (registryValue: string) =>
      new CredentialsStore().getToken(registryValue)
  )
  const storedToken = (
    options.token || process.env.SKILLHUB_TOKEN
      ? undefined
      : await getStoredToken(registry)
  )
  const token = resolveToken(options, process.env, storedToken)
  const resolveTargets = deps.resolveInstallTargets ?? resolveInstallTargets
  const targets: AgentCandidate[] = await resolveTargets({
    cwd: process.cwd(),
    scope: effectiveScope,
    dir: options.dir,
    agents: options.agent ?? [],
    json: Boolean(options.json),
    interactive: isTTY
  })
  const runInstall = deps.installCollection ?? installCollection
  const result = await runInstall({
    registry,
    token,
    namespace: parsed.namespace,
    slug: parsed.slug,
    version: options.version,
    targets,
    force: Boolean(options.force)
  })

  if (options.json) {
    return JSON.stringify({ ok: true, ...result })
  }
  return renderCollectionInstall(result)
}

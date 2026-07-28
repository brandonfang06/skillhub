import type { AgentCandidate } from '../agents/types'
import { SkillHubClient } from '../clients/skillhub-client'
import { readBoundedResponseBody } from '../platform/download'
import { installPackages } from './install-transaction'

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

export async function installSkill(
  options: InstallOptions
): Promise<{ installed: Array<{ agent: string; dir: string }> }> {
  const client = new SkillHubClient(options.registry, options.token)
  const result = await installPackages({
    registry: options.registry,
    packages: [{
      namespace: options.namespace,
      slug: options.slug,
      load: async () => {
        const resolved = await client.resolve(
          options.namespace,
          options.slug,
          options.version
        )
        const response = await client.download(
          options.namespace,
          options.slug,
          resolved.version
        )
        return {
          version: resolved.version,
          archive: await readBoundedResponseBody(response)
        }
      }
    }],
    targets: options.targets,
    force: options.force,
    home: options.home
  })

  return {
    installed: result.installed.map(({ agent, dir }) => ({ agent, dir }))
  }
}

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Copy } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { useCopyToClipboard } from '@/shared/lib/clipboard'
import {
  getBrowserAppUrl,
  getCliRegistryUrl as getRuntimeCliRegistryUrl,
} from '@/shared/lib/runtime-config'
import { normalizeInstallAgentId } from '@/features/install-selection/install-agents'
import type { InstallScope } from '@/features/install-selection/install-selection-store'

interface InstallCommandProps {
  namespace: string
  slug: string
  version?: string
}

export function buildInstallTarget(namespace: string, slug: string): string {
  return namespace === 'global' ? slug : `${namespace}--${slug}`
}

export function buildSkillhubCoordinate(namespace: string, slug: string): string {
  return `@${namespace}/${slug}`
}

/** Restrict copied commands to version tokens that are safe across common shells. */
export function isPortableSkillVersion(value: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$/.test(value)
}

export function getBaseUrl(): string {
  return getBrowserAppUrl()
}

export function getCliRegistryUrl(): string {
  return getRuntimeCliRegistryUrl()
}

export function buildInstallCommand(namespace: string, slug: string, baseUrl: string): string {
  const installTarget = buildInstallTarget(namespace, slug)
  return `npx clawhub install ${installTarget} --registry ${baseUrl}`
}

interface SkillhubInstallCommandOptions {
  scope?: InstallScope
  agentId?: string
  force?: boolean
  version?: string
}

export function buildSkillhubInstallCommand(
  namespace: string,
  slug: string,
  baseUrl: string,
  options: SkillhubInstallCommandOptions = {},
): string {
  if (options.version && !isPortableSkillVersion(options.version)) {
    return ''
  }
  const coordinate = buildSkillhubCoordinate(namespace, slug)
  const versionArg = options.version ? ` --version ${options.version}` : ''
  const scopeArg = options.scope ? ` --scope ${options.scope}` : ''
  const agentId = normalizeInstallAgentId(options.agentId)
  const agentArg = agentId ? ` --agent ${agentId}` : ''
  const forceArg = options.force ? ' --force' : ''
  return `npx @astron-team/skillhub@latest install ${coordinate}${versionArg} --registry ${baseUrl}${scopeArg}${agentArg}${forceArg}`
}

interface CommandBlockProps {
  command: string
}

const installMethodTabTriggerClass =
  "relative border-b-0 px-1 py-2 text-xs after:absolute after:bottom-[-1px] after:left-1/2 after:h-0.5 after:w-6 after:-translate-x-1/2 after:rounded-full after:bg-transparent after:content-[''] data-[state=active]:after:bg-primary"

function CommandBlock({ command }: CommandBlockProps) {
  const { t } = useTranslation()
  const [copied, copy] = useCopyToClipboard()

  const handleCopy = async () => {
    try {
      await copy(command)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  return (
    <div className="relative overflow-hidden rounded-xl border border-border/60 bg-muted/50">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={handleCopy}
        title={copied ? t('copyButton.copied') : t('copyButton.copy')}
        aria-label={copied ? t('copyButton.copied') : t('copyButton.copy')}
        className="absolute right-2 top-2 z-10 h-8 w-8 rounded-md bg-background/80 backdrop-blur hover:bg-background"
      >
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      </Button>
      <pre className="px-4 py-3 pr-14 whitespace-pre-wrap break-all">
        <code className="font-mono text-[13px] leading-relaxed text-foreground whitespace-pre-wrap break-all sm:text-sm">
          {command}
        </code>
      </pre>
    </div>
  )
}

export function InstallCommand({ namespace, slug, version }: InstallCommandProps) {
  const { t } = useTranslation()
  const registryUrl = useMemo(() => getCliRegistryUrl(), [])
  const skillhubCommand = useMemo(
    () => buildSkillhubInstallCommand(namespace, slug, registryUrl, { version }),
    [namespace, registryUrl, slug, version],
  )

  return (
    <Tabs defaultValue="skillhub" className="space-y-3">
      <TabsList className="w-full gap-6 border-border/70 bg-transparent p-0 text-xs">
        {/* ClawHub CLI is disabled for the internal deployment until ClawHub support is available.
        <TabsTrigger value="clawhub" className={installMethodTabTriggerClass}>
          {t('skillDetail.installMethodClawhub')}
        </TabsTrigger>
        */}
        <TabsTrigger value="skillhub" className={installMethodTabTriggerClass}>
          {t('skillDetail.installMethodSkillhub')}
        </TabsTrigger>
      </TabsList>
      {/* ClawHub CLI is disabled for the internal deployment until ClawHub support is available.
      <TabsContent value="clawhub">
        <CommandBlock command={clawhubCommand} />
      </TabsContent>
      */}
      <TabsContent value="skillhub">
        {skillhubCommand
          ? <CommandBlock command={skillhubCommand} />
          : <p role="alert" className="text-sm text-destructive">{t('skillDetail.installCommandUnsafeVersion')}</p>}
      </TabsContent>
    </Tabs>
  )
}

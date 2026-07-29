import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Copy } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { useCopyToClipboard } from '@/shared/lib/clipboard'

interface InstallCommandProps {
  namespace: string
  slug: string
  version?: string
}

export function buildInstallTarget(namespace: string, slug: string): string {
  return namespace === 'global' ? slug : `${namespace}--${slug}`
}

export function getBaseUrl(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  const runtimeConfig = window.__SKILLHUB_RUNTIME_CONFIG__
  const configuredUrl = runtimeConfig?.appBaseUrl
  // Use configured URL only if it's set and not localhost
  if (configuredUrl && !configuredUrl.includes('localhost')) {
    return configuredUrl
  }
  // Fallback to current page origin
  return `${window.location.protocol}//${window.location.host}`
}

export function getCliRegistryUrl(): string {
  const fallbackUrl = getBaseUrl()
  if (typeof window === 'undefined') {
    return fallbackUrl
  }

  const configuredUrl = window.__SKILLHUB_RUNTIME_CONFIG__?.cliRegistryUrl?.trim()
  if (!configuredUrl) {
    return fallbackUrl
  }

  try {
    const parsedUrl = new URL(configuredUrl)
    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
      return fallbackUrl
    }
    return configuredUrl.replace(/\/+$/, '')
  } catch {
    return fallbackUrl
  }
}

export function buildInstallCommand(namespace: string, slug: string, baseUrl: string): string {
  const installTarget = buildInstallTarget(namespace, slug)
  return `npx clawhub install ${installTarget} --registry ${baseUrl}`
}

export function buildSkillhubInstallCommand(namespace: string, slug: string, baseUrl: string): string {
  const namespaceArg = namespace === 'global' ? '' : ` --namespace ${namespace}`
  return `npx @astron-team/skillhub@latest install ${slug}${namespaceArg} --registry ${baseUrl}`
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

export function InstallCommand({ namespace, slug }: InstallCommandProps) {
  const { t } = useTranslation()
  const registryUrl = useMemo(() => getCliRegistryUrl(), [])
  const skillhubCommand = useMemo(
    () => buildSkillhubInstallCommand(namespace, slug, registryUrl),
    [namespace, registryUrl, slug],
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
        <CommandBlock command={skillhubCommand} />
      </TabsContent>
    </Tabs>
  )
}

import { useTranslation } from 'react-i18next'

import { CopyButton } from '@/shared/components/copy-button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'

export interface CollectionInstallCommandInput {
  npmRegistry: string
  packageName: string
  cliVersion: string
  skillhubBaseUrl: string
  namespace: string
  collection: string
  collectionVersion: string
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return (
      (url.protocol === 'http:' || url.protocol === 'https:') &&
      !/\s/.test(value)
    )
  } catch {
    return false
  }
}

const EXACT_VERSION = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/
const PACKAGE_NAME = /^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/
const COORDINATE = /^[a-z0-9][a-z0-9._-]*$/

export function buildCollectionInstallCommand(
  input: CollectionInstallCommandInput,
): string | null {
  if (
    !isHttpUrl(input.npmRegistry) ||
    !isHttpUrl(input.skillhubBaseUrl) ||
    !PACKAGE_NAME.test(input.packageName) ||
    !EXACT_VERSION.test(input.cliVersion) ||
    input.cliVersion.toLowerCase() === 'latest' ||
    !EXACT_VERSION.test(input.collectionVersion) ||
    !COORDINATE.test(input.namespace) ||
    !COORDINATE.test(input.collection)
  ) {
    return null
  }

  const npmRegistry = input.npmRegistry.replace(/\/$/, '')
  const skillhubBaseUrl = input.skillhubBaseUrl.replace(/\/$/, '')
  return [
    'npx',
    '--yes',
    '--registry',
    npmRegistry,
    `${input.packageName}@${input.cliVersion}`,
    'collection',
    'install',
    `@${input.namespace}/${input.collection}`,
    '--registry',
    skillhubBaseUrl,
    '--version',
    input.collectionVersion,
    '--scope',
    'user',
  ].join(' ')
}

export function CollectionInstallCommand({
  input,
}: {
  input: CollectionInstallCommandInput
}) {
  const { t } = useTranslation()
  const command = buildCollectionInstallCommand(input)

  if (!command) {
    return (
      <p className="text-sm text-muted-foreground">
        {t('collectionInstall.unavailable')}
      </p>
    )
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>{t('collectionInstall.title')}</CardTitle>
        <CopyButton
          text={command}
          ariaLabel={t('collectionInstall.copy')}
        />
      </CardHeader>
      <CardContent>
        <code
          aria-readonly="true"
          className="block overflow-x-auto rounded-lg bg-secondary/60 p-4 text-sm"
        >
          {command}
        </code>
      </CardContent>
    </Card>
  )
}

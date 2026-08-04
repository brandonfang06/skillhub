import { useTranslation } from 'react-i18next'
import { Button } from '@/shared/ui/button'
import { buildAppPath, getAppBasePath } from '@/shared/lib/runtime-config'
import { useAuthMethods } from './use-auth-methods'

interface LoginButtonProps {
  returnTo?: string
}

/**
 * Returns the appropriate icon for a given OAuth provider.
 */
export function getOAuthIconUrl(provider: string): string {
  return buildAppPath(`/${provider.toLowerCase()}-logo.svg`)
}

export function getOAuthActionUrl(actionUrl: string): string {
  if (!actionUrl.startsWith('/') || actionUrl.startsWith('//')) {
    return actionUrl
  }

  const basePath = getAppBasePath()
  if (basePath && (actionUrl === basePath || actionUrl.startsWith(`${basePath}/`))) {
    return actionUrl
  }
  return buildAppPath(actionUrl)
}

function OAuthIcon({ provider }: { provider: string }) {
  return (
    <img
      src={getOAuthIconUrl(provider)}
      alt={provider}
      className="w-5 h-5 mr-3"
    />
  )
}

/**
 * Renders OAuth login buttons from the auth-method catalog returned by the backend.
 */
export function LoginButton({ returnTo }: LoginButtonProps) {
  const { t } = useTranslation()
  const { data, isLoading } = useAuthMethods(returnTo)

  const providers = (data ?? []).filter((method) => method.methodType === 'OAUTH_REDIRECT')

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Button className="w-full h-12" disabled>
          <div className="w-5 h-5 rounded-full animate-shimmer mr-3" />
          {t('loginButton.loading')}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {providers.map((provider) => (
        <Button
          key={provider.id}
          className="w-full h-12 text-base"
          variant="outline"
          onClick={() => {
            window.location.href = getOAuthActionUrl(provider.actionUrl)
          }}
        >
          <OAuthIcon provider={provider.provider} />
          {t('loginButton.loginWith', { name: provider.displayName })}
        </Button>
      ))}
    </div>
  )
}


import { Plus, RefreshCw, ShieldOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import type { ServiceToken } from './service-principals'
import type { ServiceTokenExpiryMode } from './service-token-expiry'

interface ServiceTokenFormProps {
  tokenName: string
  expiryMode: ServiceTokenExpiryMode
  expiresOn: string
  minExpiresOn: string
  maxExpiresOn: string
  expiryError: string | null
  isPending: boolean
  disabled: boolean
  onTokenNameChange: (value: string) => void
  onExpiryModeChange: (value: ServiceTokenExpiryMode) => void
  onExpiresOnChange: (value: string) => void
  onCreate: () => void
}

export function ServiceTokenForm({
  tokenName,
  expiryMode,
  expiresOn,
  minExpiresOn,
  maxExpiresOn,
  expiryError,
  isPending,
  disabled,
  onTokenNameChange,
  onExpiryModeChange,
  onExpiresOnChange,
  onCreate,
}: ServiceTokenFormProps) {
  const { t } = useTranslation()
  const helpId = 'service-token-expiry-help'
  const neverExpires = expiryMode === 'never'

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="service-token-name">{t('servicePrincipals.tokenName')}</Label>
        <Input
          id="service-token-name"
          value={tokenName}
          maxLength={100}
          onChange={(event) => onTokenNameChange(event.target.value)}
        />
      </div>
      <label className="flex items-start gap-3 rounded-lg border p-3" htmlFor="service-token-never-expires">
        <input
          id="service-token-never-expires"
          className="mt-1 h-4 w-4"
          type="checkbox"
          checked={neverExpires}
          onChange={(event) => onExpiryModeChange(event.target.checked ? 'never' : 'expires')}
        />
        <span className="space-y-1">
          <span className="block text-sm font-medium">{t('servicePrincipals.neverExpires')}</span>
          <span className="block text-xs text-muted-foreground">
            {t('servicePrincipals.neverExpiresWarning')}
          </span>
        </span>
      </label>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <div className="min-w-0 space-y-2">
          <Label htmlFor="service-token-expiry">{t('servicePrincipals.expiryLabel')}</Label>
          <Input
            id="service-token-expiry"
            type="date"
            value={expiresOn}
            min={minExpiresOn}
            max={maxExpiresOn}
            disabled={neverExpires}
            aria-invalid={Boolean(expiryError)}
            aria-describedby={helpId}
            onChange={(event) => onExpiresOnChange(event.target.value)}
          />
          <p
            id={helpId}
            className={expiryError ? 'text-xs text-red-600' : 'text-xs text-muted-foreground'}
          >
            {expiryError ?? t('servicePrincipals.expiryHint', { date: maxExpiresOn })}
          </p>
        </div>
        <Button
          className="w-full sm:w-auto"
          disabled={disabled || !tokenName.trim() || isPending}
          onClick={onCreate}
        >
          <Plus className="mr-2 h-4 w-4" />
          {isPending ? t('servicePrincipals.creating') : t('servicePrincipals.createToken')}
        </Button>
      </div>
    </div>
  )
}

interface ServiceTokenRowProps {
  token: ServiceToken
  formattedExpiry: string
  rotateDisabled: boolean
  revokeDisabled: boolean
  onRotate: () => void
  onRevoke: () => void
}

export function ServiceTokenRow({
  token,
  formattedExpiry,
  rotateDisabled,
  revokeDisabled,
  onRotate,
  onRevoke,
}: ServiceTokenRowProps) {
  const { t } = useTranslation()
  const revoked = Boolean(token.revokedAt)

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
      <div className="min-w-0 flex-1">
        <div className="break-words font-medium">{token.name}</div>
        <div className="break-words font-mono text-xs text-muted-foreground">
          {token.tokenPrefix}… · {formattedExpiry}
        </div>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button
          variant="ghost"
          size="sm"
          disabled={rotateDisabled || revoked}
          aria-label={t('servicePrincipals.rotateToken')}
          onClick={onRotate}
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={revokeDisabled || revoked}
          aria-label={t('servicePrincipals.revokeToken')}
          onClick={onRevoke}
        >
          <ShieldOff className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

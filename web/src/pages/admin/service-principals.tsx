import { useMemo, useState } from 'react'
import { Copy, KeyRound, Plus, ShieldOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  type ServicePrincipal,
  type ServiceToken,
  type ServiceTokenSecret,
  useServicePrincipalMutations,
  useServicePrincipals,
  useServiceTokens,
} from '@/features/admin/service-principals'
import { ServiceTokenForm, ServiceTokenRow } from '@/features/admin/service-token-controls'
import {
  type ServiceTokenExpiryMode,
  serviceTokenExpiryBounds,
  serviceTokenExpiryValue,
  validateServiceTokenExpiryDate,
} from '@/features/admin/service-token-expiry'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/ui/table'

export function ServicePrincipalsPage() {
  const { t, i18n } = useTranslation()
  const principals = useServicePrincipals()
  const mutations = useServicePrincipalMutations()
  const initialExpiryBounds = useMemo(() => serviceTokenExpiryBounds(new Date()), [])
  const [expiryBounds, setExpiryBounds] = useState(initialExpiryBounds)
  const [createOpen, setCreateOpen] = useState(false)
  const [selected, setSelected] = useState<ServicePrincipal | null>(null)
  const [secret, setSecret] = useState<ServiceTokenSecret | null>(null)
  const [code, setCode] = useState('gitlab-oss-importer')
  const [displayName, setDisplayName] = useState('GitLab OSS Importer')
  const [tokenName, setTokenName] = useState('production')
  const [expiryMode, setExpiryMode] = useState<ServiceTokenExpiryMode>('expires')
  const [expiresOn, setExpiresOn] = useState(initialExpiryBounds.defaultValue)
  const tokens = useServiceTokens(selected?.id ?? null)
  const expiryIssue = validateServiceTokenExpiryDate(expiresOn, expiryBounds, expiryMode)
  const expiryError = expiryIssue === 'required'
    ? t('servicePrincipals.expiryRequired')
    : expiryIssue === 'range'
      ? t('servicePrincipals.expiryRange', { min: expiryBounds.min, max: expiryBounds.max })
      : null
  const activeCount = useMemo(
    () => principals.data?.items.filter((item) => item.status === 'ACTIVE').length ?? 0,
    [principals.data],
  )

  const createPrincipal = async () => {
    try {
      await mutations.createPrincipal.mutateAsync({ code, displayName })
      setCreateOpen(false)
      toast.success(t('servicePrincipals.created'))
    } catch (error) {
      toast.error(t('servicePrincipals.error'), error instanceof Error ? error.message : '')
    }
  }

  const createToken = async () => {
    if (!selected || expiryIssue) return
    try {
      const created = await mutations.createToken.mutateAsync({
        id: selected.id,
        name: tokenName,
        scopes: ['source:import'],
        expiresAt: serviceTokenExpiryValue(expiresOn, expiryMode),
      })
      setSecret(created)
      await tokens.refetch()
    } catch (error) {
      toast.error(t('servicePrincipals.error'), error instanceof Error ? error.message : '')
    }
  }

  const rotateToken = async (token: ServiceToken) => {
    if (expiryIssue) return
    try {
      const rotated = await mutations.rotateToken.mutateAsync({
        id: token.servicePrincipalId,
        tokenId: token.id,
        expiresAt: serviceTokenExpiryValue(expiresOn, expiryMode),
      })
      setSecret(rotated)
      await tokens.refetch()
    } catch (error) {
      toast.error(t('servicePrincipals.error'), error instanceof Error ? error.message : '')
    }
  }

  const revokeToken = async (token: ServiceToken) => {
    try {
      await mutations.revokeToken.mutateAsync({
        id: token.servicePrincipalId,
        tokenId: token.id,
      })
      await tokens.refetch()
    } catch (error) {
      toast.error(t('servicePrincipals.error'), error instanceof Error ? error.message : '')
    }
  }

  const toggleStatus = async (principal: ServicePrincipal) => {
    await mutations.updatePrincipal.mutateAsync({
      id: principal.id,
      status: principal.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE',
    })
  }

  const manageTokens = (principal: ServicePrincipal) => {
    const nextBounds = serviceTokenExpiryBounds(new Date())
    setExpiryBounds(nextBounds)
    setExpiresOn(nextBounds.defaultValue)
    setExpiryMode('expires')
    setSelected(principal)
  }

  return (
    <div className="space-y-8 animate-fade-up">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-4xl font-bold font-heading">{t('servicePrincipals.title')}</h1>
          <p className="mt-2 max-w-3xl text-lg text-muted-foreground">{t('servicePrincipals.subtitle')}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}><Plus className="mr-2 h-4 w-4" />{t('servicePrincipals.create')}</Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="p-5"><div className="text-sm text-muted-foreground">{t('servicePrincipals.total')}</div><div className="mt-2 text-3xl font-semibold">{principals.data?.total ?? 0}</div></Card>
        <Card className="p-5"><div className="text-sm text-muted-foreground">{t('servicePrincipals.active')}</div><div className="mt-2 text-3xl font-semibold">{activeCount}</div></Card>
        <Card className="p-5"><div className="text-sm text-muted-foreground">{t('servicePrincipals.tokens')}</div><div className="mt-2 text-3xl font-semibold">{principals.data?.items.reduce((sum, item) => sum + item.activeTokenCount, 0) ?? 0}</div></Card>
      </div>

      <Card className="overflow-hidden">
        <Table>
          <TableHeader><TableRow><TableHead>{t('servicePrincipals.identity')}</TableHead><TableHead>{t('servicePrincipals.status')}</TableHead><TableHead>{t('servicePrincipals.tokens')}</TableHead><TableHead>{t('servicePrincipals.lastUsed')}</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {principals.data?.items.map((principal) => (
              <TableRow key={principal.id}>
                <TableCell><div className="font-medium">{principal.displayName}</div><div className="font-mono text-xs text-muted-foreground">{principal.code}</div></TableCell>
                <TableCell><span className={principal.status === 'ACTIVE' ? 'text-emerald-500' : 'text-muted-foreground'}>{principal.status}</span></TableCell>
                <TableCell>{principal.activeTokenCount}</TableCell>
                <TableCell>{principal.lastUsedAt ? formatLocalDateTime(principal.lastUsedAt, i18n.language) : '—'}</TableCell>
                <TableCell className="text-right"><div className="flex justify-end gap-2"><Button variant="outline" size="sm" onClick={() => manageTokens(principal)}><KeyRound className="mr-2 h-4 w-4" />{t('servicePrincipals.manageTokens')}</Button><Button variant="ghost" size="sm" onClick={() => toggleStatus(principal)}><ShieldOff className="mr-2 h-4 w-4" />{principal.status === 'ACTIVE' ? t('servicePrincipals.disable') : t('servicePrincipals.enable')}</Button></div></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent><DialogHeader><DialogTitle>{t('servicePrincipals.create')}</DialogTitle><DialogDescription>{t('servicePrincipals.createHint')}</DialogDescription></DialogHeader><div className="space-y-4"><div><Label htmlFor="service-code">{t('servicePrincipals.code')}</Label><Input id="service-code" value={code} onChange={(event) => setCode(event.target.value)} /></div><div><Label htmlFor="service-name">{t('servicePrincipals.displayName')}</Label><Input id="service-name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></div></div><DialogFooter><Button variant="outline" onClick={() => setCreateOpen(false)}>{t('dialog.cancel')}</Button><Button disabled={mutations.createPrincipal.isPending} onClick={createPrincipal}>{t('servicePrincipals.create')}</Button></DialogFooter></DialogContent>
      </Dialog>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => { if (!open) setSelected(null) }}>
        <DialogContent className="max-w-3xl"><DialogHeader><DialogTitle>{selected?.displayName}</DialogTitle><DialogDescription>{t('servicePrincipals.tokenHint')}</DialogDescription></DialogHeader><ServiceTokenForm tokenName={tokenName} expiryMode={expiryMode} expiresOn={expiresOn} minExpiresOn={expiryBounds.min} maxExpiresOn={expiryBounds.max} expiryError={expiryError} isPending={mutations.createToken.isPending} disabled={Boolean(expiryIssue)} onTokenNameChange={setTokenName} onExpiryModeChange={setExpiryMode} onExpiresOnChange={setExpiresOn} onCreate={createToken} /><div className="space-y-2">{tokens.data?.items.map((token) => <ServiceTokenRow key={token.id} token={token} formattedExpiry={token.expiresAt ? formatLocalDateTime(token.expiresAt, i18n.language) : t('servicePrincipals.neverExpires')} rotateDisabled={Boolean(expiryIssue) || mutations.rotateToken.isPending} revokeDisabled={mutations.revokeToken.isPending} onRotate={() => rotateToken(token)} onRevoke={() => revokeToken(token)} />)}</div></DialogContent>
      </Dialog>

      <Dialog open={Boolean(secret)} onOpenChange={(open) => { if (!open) setSecret(null) }}>
        <DialogContent><DialogHeader><DialogTitle>{t('servicePrincipals.secretTitle')}</DialogTitle><DialogDescription>{t('servicePrincipals.secretWarning')}</DialogDescription></DialogHeader><div className="break-all rounded-lg bg-muted p-4 font-mono text-sm" data-testid="service-token-secret">{secret?.token}</div><DialogFooter><Button onClick={async () => { if (!secret) return; await navigator.clipboard.writeText(secret.token); toast.success(t('servicePrincipals.copied')) }}><Copy className="mr-2 h-4 w-4" />{t('servicePrincipals.copy')}</Button><Button variant="outline" onClick={() => setSecret(null)}>{t('dialog.close')}</Button></DialogFooter></DialogContent>
      </Dialog>
    </div>
  )
}

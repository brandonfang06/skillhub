import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useAddAdminNamespaceMember,
  useAdminNamespace,
  useAdminNamespaceCandidates,
  useAdminNamespaceMembers,
  useAdminNamespaces,
  useArchiveAdminNamespace,
  useFreezeAdminNamespace,
  useRemoveAdminNamespaceMember,
  useRestoreAdminNamespace,
  useTransferAdminNamespaceOwnership,
  useUnfreezeAdminNamespace,
  useUpdateAdminNamespaceMemberRole,
  type AdminNamespaceMember,
  type AdminNamespace,
  type AdminNamespaceRole,
  type AdminNamespaceStatus,
  type AdminNamespaceType,
} from '@/features/admin/use-admin-namespaces'
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

type LifecycleAction = 'freeze' | 'unfreeze' | 'archive' | 'restore'
type ActionTarget = { slug: string; displayName: string }
type LifecycleDialogState = { action: LifecycleAction; target: ActionTarget } | null
type MemberAction = {
  type: 'remove' | 'transfer' | 'role'
  member: AdminNamespaceMember
  target: ActionTarget
  role?: AdminNamespaceRole
} | null
const MEMBER_PAGE_SIZE = 20

export function getAdminNamespaceLifecycleActions(
  namespace: Pick<AdminNamespace, 'permissions'>,
): LifecycleAction[] {
  if (namespace.permissions.immutable) return []
  return [
    namespace.permissions.canFreeze ? 'freeze' : null,
    namespace.permissions.canUnfreeze ? 'unfreeze' : null,
    namespace.permissions.canArchive ? 'archive' : null,
    namespace.permissions.canRestore ? 'restore' : null,
  ].filter((action): action is LifecycleAction => action !== null)
}

function StatusBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex rounded-full border px-2.5 py-1 text-xs font-medium">
      {label}
    </span>
  )
}

function LoadingBlock({ testId }: { testId: string }) {
  return (
    <div data-testid={testId} className="space-y-3" aria-busy="true">
      <div className="h-12 animate-shimmer rounded-lg" />
      <div className="h-32 animate-shimmer rounded-lg" />
    </div>
  )
}

export function AdminNamespacesPage() {
  const { t } = useTranslation()
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<AdminNamespaceStatus | ''>('')
  const [type, setType] = useState<AdminNamespaceType | ''>('')
  const [page, setPage] = useState(0)
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [candidateSearch, setCandidateSearch] = useState('')
  const [newMemberRole, setNewMemberRole] = useState<AdminNamespaceRole>('MEMBER')
  const [lifecycleDialog, setLifecycleDialog] = useState<LifecycleDialogState>(null)
  const [reason, setReason] = useState('')
  const [memberAction, setMemberAction] = useState<MemberAction>(null)
  const [memberPage, setMemberPage] = useState(0)

  const listQuery = useAdminNamespaces({
    keyword: keyword || undefined,
    status: status || undefined,
    type: type || undefined,
    page,
    size: 20,
  })
  const effectiveSlug = selectedSlug ?? listQuery.data?.items[0]?.slug ?? null
  const detailQuery = useAdminNamespace(effectiveSlug)
  const membersQuery = useAdminNamespaceMembers(effectiveSlug, memberPage, MEMBER_PAGE_SIZE)
  const candidatesQuery = useAdminNamespaceCandidates(effectiveSlug, candidateSearch)
  const addMember = useAddAdminNamespaceMember()
  const updateRole = useUpdateAdminNamespaceMemberRole()
  const removeMember = useRemoveAdminNamespaceMember()
  const transferOwnership = useTransferAdminNamespaceOwnership()
  const freeze = useFreezeAdminNamespace()
  const unfreeze = useUnfreezeAdminNamespace()
  const archive = useArchiveAdminNamespace()
  const restore = useRestoreAdminNamespace()

  const detail = detailQuery.data
  const members = membersQuery.data?.items ?? []

  useEffect(() => {
    setMemberPage(0)
  }, [effectiveSlug])

  const applySearch = () => {
    setKeyword(keywordInput.trim())
    setPage(0)
    setSelectedSlug(null)
  }

  const runMutation = async (operation: () => Promise<unknown>) => {
    try {
      await operation()
      toast.success(t('adminNamespaces.success'))
      return true
    } catch {
      toast.error(t('adminNamespaces.error.mutation'))
      return false
    }
  }

  const confirmLifecycle = async () => {
    if (!lifecycleDialog) return
    const input = { slug: lifecycleDialog.target.slug, reason: reason.trim() || undefined }
    const mutation = {
      freeze: () => freeze.mutateAsync(input),
      unfreeze: () => unfreeze.mutateAsync(input),
      archive: () => archive.mutateAsync(input),
      restore: () => restore.mutateAsync(input),
    }[lifecycleDialog.action]
    if (await runMutation(mutation)) {
      closeLifecycleDialog()
    }
  }

  const closeLifecycleDialog = () => {
    setLifecycleDialog(null)
    setReason('')
  }

  const confirmMemberAction = async () => {
    if (!memberAction) return
    const input = { slug: memberAction.target.slug, userId: memberAction.member.userId }
    const operation = memberAction.type === 'remove'
      ? () => removeMember.mutateAsync(input)
      : memberAction.type === 'transfer'
        ? () => transferOwnership.mutateAsync({ slug: memberAction.target.slug, newOwnerId: memberAction.member.userId })
        : () => updateRole.mutateAsync({ ...input, role: memberAction.role! })
    if (await runMutation(operation)) setMemberAction(null)
  }

  const stats = listQuery.data?.stats
  const lifecyclePending = freeze.isPending || unfreeze.isPending || archive.isPending || restore.isPending
  const lifecycleActions = detail ? getAdminNamespaceLifecycleActions(detail) : []
  const actionTarget = detail ? { slug: detail.slug, displayName: detail.displayName } : null

  return (
    <main className="min-w-0 space-y-6 animate-fade-up">
      <header>
        <h1 className="break-words text-3xl font-bold font-heading sm:text-4xl">{t('adminNamespaces.title')}</h1>
        <p className="mt-2 text-muted-foreground">{t('adminNamespaces.subtitle')}</p>
      </header>

      <section aria-label={t('adminNamespaces.stats.label')} className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {(['total', 'active', 'frozen', 'archived'] as const).map((key) => (
          <Card key={key} className="min-w-0 p-4">
            <p className="text-xs text-muted-foreground">{t(`adminNamespaces.stats.${key}`)}</p>
            <p className="mt-1 text-2xl font-semibold">{stats?.[key] ?? '—'}</p>
          </Card>
        ))}
      </section>

      <Card className="p-4">
        <form
          className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto]"
          onSubmit={(event) => { event.preventDefault(); applySearch() }}
        >
          <div className="min-w-0 space-y-2">
            <Label htmlFor="admin-namespace-search">{t('adminNamespaces.filter.keyword')}</Label>
            <Input
              id="admin-namespace-search"
              value={keywordInput}
              onChange={(event) => setKeywordInput(event.target.value)}
              placeholder={t('adminNamespaces.filter.keywordPlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="admin-namespace-status">{t('adminNamespaces.filter.status')}</Label>
            <select
              id="admin-namespace-status"
              className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              value={status}
              onChange={(event) => { setStatus(event.target.value as AdminNamespaceStatus | ''); setPage(0); setSelectedSlug(null) }}
            >
              <option value="">{t('adminNamespaces.filter.all')}</option>
              <option value="ACTIVE">{t('adminNamespaces.status.ACTIVE')}</option>
              <option value="FROZEN">{t('adminNamespaces.status.FROZEN')}</option>
              <option value="ARCHIVED">{t('adminNamespaces.status.ARCHIVED')}</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="admin-namespace-type">{t('adminNamespaces.filter.type')}</Label>
            <select
              id="admin-namespace-type"
              className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              value={type}
              onChange={(event) => { setType(event.target.value as AdminNamespaceType | ''); setPage(0); setSelectedSlug(null) }}
            >
              <option value="">{t('adminNamespaces.filter.all')}</option>
              <option value="TEAM">{t('adminNamespaces.type.TEAM')}</option>
              <option value="GLOBAL">{t('adminNamespaces.type.GLOBAL')}</option>
            </select>
          </div>
          <Button type="submit" className="self-end">{t('adminNamespaces.filter.search')}</Button>
        </form>
      </Card>

      {listQuery.isLoading ? <LoadingBlock testId="admin-namespaces-loading" /> : listQuery.isError ? (
        <Card className="p-6 text-center" role="alert">
          <p>{t('adminNamespaces.error.list')}</p>
          <Button className="mt-3" variant="outline" onClick={() => listQuery.refetch()}>{t('adminNamespaces.retry')}</Button>
        </Card>
      ) : listQuery.data?.items.length === 0 ? (
        <Card className="p-8 text-center text-muted-foreground">{t('adminNamespaces.empty')}</Card>
      ) : (
        <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(280px,0.85fr)_minmax(0,1.65fr)]">
          <section className="min-w-0 space-y-3" aria-label={t('adminNamespaces.listLabel')}>
            {listQuery.data?.items.map((namespace) => (
              <button
                key={namespace.slug}
                type="button"
                onClick={() => { setSelectedSlug(namespace.slug); setMemberPage(0) }}
                className={`w-full min-w-0 rounded-xl border p-4 text-left transition-colors hover:bg-muted/50 ${effectiveSlug === namespace.slug ? 'border-primary bg-primary/5' : ''}`}
              >
                <div className="flex min-w-0 items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="break-words font-semibold">{namespace.displayName}</p>
                    <p className="break-all text-xs text-muted-foreground">@{namespace.slug}</p>
                  </div>
                  <StatusBadge label={t(`adminNamespaces.status.${namespace.status}`)} />
                </div>
                <p className="mt-3 text-sm text-muted-foreground">
                  {t('adminNamespaces.counts', namespace.stats)}
                </p>
              </button>
            ))}
            <div className="flex items-center justify-between gap-3">
              <Button variant="outline" disabled={page === 0} onClick={() => { setPage((value) => value - 1); setSelectedSlug(null) }}>{t('adminNamespaces.previous')}</Button>
              <span className="text-sm text-muted-foreground">{page + 1}</span>
              <Button variant="outline" disabled={(page + 1) * 20 >= (listQuery.data?.total ?? 0)} onClick={() => { setPage((value) => value + 1); setSelectedSlug(null) }}>{t('adminNamespaces.next')}</Button>
            </div>
          </section>

          <section className="min-w-0 space-y-5" aria-label={t('adminNamespaces.detailLabel')}>
            {detailQuery.isLoading ? <LoadingBlock testId="admin-namespace-detail-loading" /> : detailQuery.isError ? (
              <Card className="p-6" role="alert">
                <p>{t('adminNamespaces.error.detail')}</p>
                <Button className="mt-3" variant="outline" onClick={() => detailQuery.refetch()}>{t('adminNamespaces.retry')}</Button>
              </Card>
            ) : detail ? (
              <>
                <Card className="min-w-0 p-5">
                  <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <h2 className="break-words text-2xl font-semibold">{detail.displayName}</h2>
                      <p className="break-all text-sm text-muted-foreground">@{detail.slug}</p>
                      {detail.description ? <p className="mt-3 break-words text-sm">{detail.description}</p> : null}
                    </div>
                    <div className="flex flex-wrap gap-2"><StatusBadge label={t(`adminNamespaces.type.${detail.type}`)} /><StatusBadge label={t(`adminNamespaces.status.${detail.status}`)} /></div>
                  </div>
                  <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
                    <div><dt className="text-muted-foreground">{t('adminNamespaces.currentRole')}</dt><dd className="break-words font-medium">{detail.permissions.currentUserRole ? t(`adminNamespaces.role.${detail.permissions.currentUserRole}`) : t('adminNamespaces.noMembership')}</dd></div>
                    <div><dt className="text-muted-foreground">{t('adminNamespaces.platformOverride')}</dt><dd className="font-medium">{detail.permissions.platformOverride ? t('adminNamespaces.yes') : t('adminNamespaces.no')}</dd></div>
                    <div><dt className="text-muted-foreground">{t('adminNamespaces.memberCount')}</dt><dd>{detail.stats.memberCount}</dd></div>
                    <div><dt className="text-muted-foreground">{t('adminNamespaces.skillCount')}</dt><dd>{detail.stats.skillCount}</dd></div>
                  </dl>
                  {detail.permissions.immutable ? (
                    <p className="mt-4 rounded-lg border p-3 text-sm text-muted-foreground">{t('adminNamespaces.globalReadOnly')}</p>
                  ) : (
                    <div className="mt-5 flex flex-wrap gap-2">
                      {lifecycleActions.map((action) => (
                        <Button
                          key={action}
                          variant={action === 'archive' ? 'destructive' : 'outline'}
                          onClick={() => actionTarget && setLifecycleDialog({ action, target: actionTarget })}
                        >
                          {t(`adminNamespaces.actions.${action}`)}
                        </Button>
                      ))}
                    </div>
                  )}
                </Card>

                <Card className="min-w-0 p-5">
                  <h3 className="text-lg font-semibold">{t('adminNamespaces.members.title')}</h3>
                  {detail.permissions.canManageMembers ? (
                    <div className="mt-4 grid min-w-0 gap-3 sm:grid-cols-[minmax(0,1fr)_150px]">
                      <div className="space-y-2">
                        <Label htmlFor="admin-namespace-candidate">{t('adminNamespaces.members.search')}</Label>
                        <Input id="admin-namespace-candidate" value={candidateSearch} onChange={(event) => setCandidateSearch(event.target.value)} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="admin-new-member-role">{t('adminNamespaces.members.role')}</Label>
                        <select id="admin-new-member-role" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={newMemberRole} onChange={(event) => setNewMemberRole(event.target.value as AdminNamespaceRole)}>
                          <option value="MEMBER">{t('adminNamespaces.role.MEMBER')}</option><option value="ADMIN">{t('adminNamespaces.role.ADMIN')}</option>
                        </select>
                      </div>
                      {candidatesQuery.data?.map((candidate) => (
                        <div key={candidate.userId} className="flex min-w-0 items-center justify-between gap-3 rounded-lg border p-3 sm:col-span-2">
                          <div className="min-w-0"><p className="break-words font-medium">{candidate.displayName}</p><p className="break-all text-xs text-muted-foreground">{candidate.email ?? candidate.userId}</p></div>
                          <Button size="sm" disabled={addMember.isPending} onClick={() => runMutation(() => addMember.mutateAsync({ slug: detail.slug, userId: candidate.userId, role: newMemberRole }))}>{t('adminNamespaces.members.add')}</Button>
                        </div>
                      ))}
                      {candidatesQuery.isFetching ? <p className="text-sm text-muted-foreground sm:col-span-2">{t('adminNamespaces.members.searching')}</p> : null}
                      {candidatesQuery.isError ? (
                        <div className="sm:col-span-2" role="alert">
                          <p className="text-sm text-destructive">{t('adminNamespaces.error.candidates')}</p>
                          <Button variant="outline" size="sm" onClick={() => candidatesQuery.refetch()}>{t('adminNamespaces.retry')}</Button>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {membersQuery.isLoading ? <LoadingBlock testId="admin-namespace-members-loading" /> : membersQuery.isError ? (
                    <div className="mt-4" role="alert"><p>{t('adminNamespaces.error.members')}</p><Button variant="outline" onClick={() => membersQuery.refetch()}>{t('adminNamespaces.retry')}</Button></div>
                  ) : (
                    <div className="mt-4 space-y-3">
                      {members.length === 0 ? <p className="text-sm text-muted-foreground">{t('adminNamespaces.members.empty')}</p> : null}
                      {members.map((member) => (
                        <div key={member.userId} className="flex min-w-0 flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between">
                          <div className="min-w-0"><p className="break-words font-medium">{member.displayName || member.userId}</p><p className="break-all text-xs text-muted-foreground">{member.email || member.userId}</p></div>
                          <div className="flex flex-wrap items-center gap-2">
                            {detail.permissions.canManageMembers && member.role !== 'OWNER' ? (
                              <select
                                aria-label={t('adminNamespaces.members.changeRole')}
                                className="h-9 rounded-md border bg-background px-2 text-sm"
                                value={member.role}
                                onChange={(event) => actionTarget && setMemberAction({
                                  type: 'role',
                                  member,
                                  target: actionTarget,
                                  role: event.target.value as AdminNamespaceRole,
                                })}
                              >
                                <option value="MEMBER">{t('adminNamespaces.role.MEMBER')}</option><option value="ADMIN">{t('adminNamespaces.role.ADMIN')}</option>
                              </select>
                            ) : <StatusBadge label={t(`adminNamespaces.role.${member.role}`)} />}
                            {detail.permissions.canTransferOwnership && member.role !== 'OWNER' && actionTarget ? <Button size="sm" variant="outline" onClick={() => setMemberAction({ type: 'transfer', member, target: actionTarget })}>{t('adminNamespaces.members.transfer')}</Button> : null}
                            {detail.permissions.canManageMembers && member.role !== 'OWNER' && actionTarget ? <Button size="sm" variant="destructive" onClick={() => setMemberAction({ type: 'remove', member, target: actionTarget })}>{t('adminNamespaces.members.remove')}</Button> : null}
                          </div>
                        </div>
                      ))}
                      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
                        <p className="text-sm text-muted-foreground">
                          {t('adminNamespaces.members.total', {
                            total: membersQuery.data?.total ?? 0,
                            page: memberPage + 1,
                          })}
                        </p>
                        <div className="flex gap-2">
                          <Button variant="outline" size="sm" disabled={memberPage === 0} onClick={() => setMemberPage((value) => value - 1)}>{t('adminNamespaces.members.previous')}</Button>
                          <Button variant="outline" size="sm" disabled={(memberPage + 1) * MEMBER_PAGE_SIZE >= (membersQuery.data?.total ?? 0)} onClick={() => setMemberPage((value) => value + 1)}>{t('adminNamespaces.members.next')}</Button>
                        </div>
                      </div>
                    </div>
                  )}
                </Card>
              </>
            ) : null}
          </section>
        </div>
      )}

      <Dialog open={lifecycleDialog !== null} onOpenChange={(open) => { if (!open) closeLifecycleDialog() }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t(`adminNamespaces.confirm.${lifecycleDialog?.action ?? 'freeze'}.title`)}</DialogTitle><DialogDescription>{t(`adminNamespaces.confirm.${lifecycleDialog?.action ?? 'freeze'}.description`, { slug: lifecycleDialog?.target.slug, namespace: lifecycleDialog?.target.displayName })}</DialogDescription></DialogHeader>
          {lifecycleDialog?.action === 'freeze' || lifecycleDialog?.action === 'archive' ? <div className="space-y-2"><Label htmlFor="admin-namespace-reason">{t('adminNamespaces.confirm.reason')}</Label><textarea id="admin-namespace-reason" maxLength={512} value={reason} onChange={(event) => setReason(event.target.value)} className="min-h-24 w-full rounded-md border bg-background p-3 text-sm" /><p className="text-right text-xs text-muted-foreground">{reason.length}/512</p></div> : null}
          <DialogFooter><Button variant="outline" onClick={closeLifecycleDialog}>{t('dialog.cancel')}</Button><Button variant={lifecycleDialog?.action === 'archive' ? 'destructive' : 'default'} disabled={lifecyclePending || reason.length > 512} onClick={confirmLifecycle}>{t('dialog.confirm')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={memberAction !== null} onOpenChange={(open) => { if (!open) setMemberAction(null) }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t(`adminNamespaces.confirm.${memberAction?.type ?? 'remove'}.title`)}</DialogTitle><DialogDescription className="break-all">{t(`adminNamespaces.confirm.${memberAction?.type ?? 'remove'}.description`, { user: memberAction?.member.displayName || memberAction?.member.userId, slug: memberAction?.target.slug, namespace: memberAction?.target.displayName, role: memberAction?.role ? t(`adminNamespaces.role.${memberAction.role}`) : undefined })}</DialogDescription></DialogHeader>
          <DialogFooter><Button variant="outline" onClick={() => setMemberAction(null)}>{t('dialog.cancel')}</Button><Button variant={memberAction?.type === 'remove' ? 'destructive' : 'default'} disabled={removeMember.isPending || transferOwnership.isPending || updateRole.isPending} onClick={confirmMemberAction}>{t('dialog.confirm')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  )
}

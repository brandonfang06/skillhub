import { useEffect, useState } from 'react'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Folder } from 'lucide-react'
import { useAuth } from '@/features/auth/use-auth'
import {
  buildGlobalReviewsPath,
  buildNamespaceReviewDetailPath,
  buildNamespaceReviewsPath,
  canAccessGlobalReviewCenter,
} from '@/features/review/review-paths'
import { formatLocalDateTime } from '@/shared/lib/date-time'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { Textarea } from '@/shared/ui/textarea'
import { Label } from '@/shared/ui/label'
import { ConfirmDialog } from '@/shared/components/confirm-dialog'
import { toast } from '@/shared/lib/toast'
import { cn } from '@/shared/lib/utils'
import { resolveReviewActionErrorDescription } from '@/features/review/review-error'
import { ReviewSkillDetailSection } from '@/features/review/review-skill-detail-section'
import { ScanOverrideDialog } from '@/features/review/scan-override-dialog'
import { SecurityAuditSection } from '@/features/security-audit/security-audit-section'
import { useSecurityAudits } from '@/features/security-audit/use-security-audit'
import { FileTree } from '@/features/skill/file-tree'
import { FilePreviewDialog } from '@/features/skill/file-preview-dialog'
import type { FileTreeNode } from '@/features/skill/file-tree-builder'
import { useReviewFile } from '@/features/review/use-review-file'
import { buildApiUrl, WEB_API_PREFIX } from '@/api/client'
import { useReviewDetail, useReviewSkillDetail, useApproveReview, useRejectReview } from '@/features/review/use-review-detail'

/**
 * Review task detail page for moderators. The route owns the approve/reject
 * interaction state because both actions depend on route-local confirmation
 * dialogs, comment input, and redirect behavior after completion.
 */
function ReviewDetailScreen({
  taskId,
  backTo,
  namespaceSlug,
}: {
  taskId: number
  backTo: string
  namespaceSlug?: string
}) {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const { user } = useAuth()

  const { data: review, isLoading } = useReviewDetail(taskId)
  const {
    data: reviewSkillDetail,
    isLoading: isLoadingReviewSkillDetail,
    error: reviewSkillDetailError,
  } = useReviewSkillDetail(
    taskId,
    Boolean(review && review.artifactAvailable !== false),
  )
  const approveMutation = useApproveReview({
    onSuccess: () => {
      toast.success(t('review.approveSuccess'))
      navigate({ to: backTo })
    },
    onError: (error) => {
      toast.error(t('review.approveFailed'), resolveReviewActionErrorDescription(error))
    },
  })
  const rejectMutation = useRejectReview({
    onSuccess: () => {
      toast.success(t('review.rejectSuccess'))
      navigate({ to: backTo })
    },
    onError: (error) => {
      toast.error(t('review.rejectFailed'), resolveReviewActionErrorDescription(error))
    },
  })

  const [comment, setComment] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [approveDialog, setApproveDialog] = useState(false)
  const [scanOverrideDialog, setScanOverrideDialog] = useState(false)
  const [rejectDialog, setRejectDialog] = useState(false)
  // File browser sidebar state
  const [fileBrowserOpen, setFileBrowserOpen] = useState(true)
  const [previewNode, setPreviewNode] = useState<FileTreeNode | null>(null)
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false)
  const hasGlobalReviewAccess = canAccessGlobalReviewCenter(user?.platformRoles)
  const shouldRedirectToNamespaceRoute =
    !namespaceSlug &&
    !!review &&
    review.namespace !== 'global' &&
    !hasGlobalReviewAccess
  const activeReviewVersion = reviewSkillDetail?.versions?.find(
    (version) => version.version === reviewSkillDetail.activeVersion
  )
  const skillId = reviewSkillDetail?.skill?.id
  const versionId = activeReviewVersion?.id ?? review?.skillVersionId
  const {
    data: securityAudits,
    isLoading: isLoadingSecurityAudits,
    error: securityAuditError,
  } = useSecurityAudits(
    skillId,
    versionId,
    activeReviewVersion?.status,
  )
  const scannerAudit = securityAudits?.find(
    (audit) => audit.scannerType.toLowerCase().replace(/_/g, '-') === 'skill-scanner'
  )
  const isPartialScan = scannerAudit?.scanStatus === 'PARTIAL'
  const canOverridePartialScan = Boolean(
    user?.platformRoles?.some((role) => role === 'SKILL_ADMIN' || role === 'SUPER_ADMIN')
  )

  // File content for preview — uses the review-bound version via review file API
  const { data: previewContent, isLoading: isLoadingPreview, error: previewError } = useReviewFile(
    taskId,
    previewNode?.path || null,
    previewDialogOpen && !!previewNode
  )

  const handleFileClick = (node: FileTreeNode) => {
    setPreviewNode(node)
    setPreviewDialogOpen(true)
  }

  const handleDownloadFile = () => {
    if (!previewNode) return
    const url = buildApiUrl(`${WEB_API_PREFIX}/reviews/${taskId}/file?path=${encodeURIComponent(previewNode.path)}`)
    const link = document.createElement('a')
    link.href = url
    link.download = previewNode.name
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  const formatDate = (dateString: string) => {
    return formatLocalDateTime(dateString, i18n.language)
  }

  useEffect(() => {
    if (!shouldRedirectToNamespaceRoute || !review) {
      return
    }

    void navigate({
      to: buildNamespaceReviewDetailPath(review.namespace, review.id),
      replace: true,
    })
  }, [navigate, review, shouldRedirectToNamespaceRoute])

  const handleApprove = async () => {
    approveMutation.mutate({ taskId, comment: comment || undefined })
  }

  const handleScanOverrideApprove = (reason: string) => {
    approveMutation.mutate({
      taskId,
      comment: comment || undefined,
      confirmScanOverride: true,
      scanOverrideReason: reason,
    })
  }

  const handleReject = async () => {
    if (!comment.trim()) {
      toast.error(t('review.rejectReasonRequired'))
      return
    }
    rejectMutation.mutate({ taskId, comment })
  }

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-3xl animate-fade-up">
        <div className="h-10 w-48 animate-shimmer rounded-lg" />
        <div className="h-64 animate-shimmer rounded-xl" />
      </div>
    )
  }

  if (shouldRedirectToNamespaceRoute) {
    return null
  }

  if (!review) {
    return (
      <div className="text-center py-20 animate-fade-up">
        <h2 className="text-2xl font-bold font-heading mb-2">{t('review.notFound')}</h2>
      </div>
    )
  }

  const hasNamespaceMismatch = Boolean(namespaceSlug && review.namespace !== namespaceSlug)

  if (hasNamespaceMismatch) {
    return (
      <div className="space-y-6 max-w-3xl animate-fade-up">
        <div className="text-center py-20">
          <h2 className="text-2xl font-bold font-heading mb-2">{t('review.notFound')}</h2>
        </div>
        <div className="flex justify-center">
          <Button variant="outline" onClick={() => navigate({ to: backTo })}>
            {t('review.backToList')}
          </Button>
        </div>
      </div>
    )
  }

  const reviewFiles = reviewSkillDetail?.files
  const approvalBlockReason =
    isLoadingReviewSkillDetail || (skillId && versionId && isLoadingSecurityAudits)
      ? 'review.approveDisabledAuditLoading'
      : reviewSkillDetailError || !skillId || !versionId || securityAuditError
        ? 'review.approveDisabledAuditUnavailable'
        : activeReviewVersion?.status === 'SCANNING' || scannerAudit?.scanStatus === 'PENDING'
          ? 'review.approveDisabledScanning'
          : activeReviewVersion?.status === 'SCAN_FAILED' || scannerAudit?.scanStatus === 'FAILED'
            ? 'review.approveDisabledScanFailed'
            : isPartialScan && !canOverridePartialScan
              ? 'review.approveDisabledPartialNamespace'
              : null
  const isApprovalBlocked = approvalBlockReason !== null
  const replacementReviewPath = review.replacementReviewTaskId
    ? review.namespace === 'global'
      ? `/dashboard/reviews/${review.replacementReviewTaskId}`
      : buildNamespaceReviewDetailPath(review.namespace, review.replacementReviewTaskId)
    : null

  return (
    <div className="max-w-6xl mx-auto flex flex-col lg:flex-row gap-8 animate-fade-up">
      {/* Main Content */}
      <div className="flex-1 min-w-0 space-y-8">
        <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold font-heading mb-2">{t('review.detail')}</h1>
          <p className="text-muted-foreground">{t('review.id')}: {review.id}</p>
        </div>
        <Button variant="outline" onClick={() => navigate({ to: backTo })}>
          {t('review.backToList')}
        </Button>
      </div>

      <Card className="p-8 space-y-6">
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('review.namespace')}</Label>
            <p className="font-semibold font-mono">{review.namespace}/{review.skillSlug}</p>
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('review.version')}</Label>
            <p className="font-semibold">
              <span className="px-2.5 py-0.5 rounded-full bg-primary/10 text-primary text-sm font-mono">
                {review.version}
              </span>
            </p>
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('review.status')}</Label>
            <p className="font-semibold">
              {review.status === 'PENDING' && (
                <span className="px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-sm">{t('review.statusPending')}</span>
              )}
              {review.status === 'APPROVED' && (
                <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 text-sm">{t('review.statusApproved')}</span>
              )}
              {review.status === 'REJECTED' && (
                <span className="px-2.5 py-0.5 rounded-full bg-red-500/10 text-red-400 text-sm">{t('review.statusRejected')}</span>
              )}
            </p>
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('review.submitter')}</Label>
            <p className="font-semibold">{review.submittedByName || review.submittedBy}</p>
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('review.submitTime')}</Label>
            <p className="font-semibold text-muted-foreground">{formatDate(review.submittedAt)}</p>
          </div>
          {review.reviewedBy && (
            <>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('review.reviewer')}</Label>
                <p className="font-semibold">{review.reviewedByName || review.reviewedBy}</p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('review.reviewTime')}</Label>
                <p className="font-semibold text-muted-foreground">
                  {review.reviewedAt ? formatDate(review.reviewedAt) : '—'}
                </p>
              </div>
            </>
          )}
        </div>

        {review.reviewComment && (
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('review.reviewComment')}</Label>
            <p className="p-4 bg-secondary/50 rounded-xl text-sm leading-relaxed">{review.reviewComment}</p>
          </div>
        )}
      </Card>

      {review.superseded && (
        <Card data-archived-review className="border-amber-500/35 bg-amber-500/5 p-6 space-y-5">
          <div className="space-y-2">
            <h2 className="text-xl font-bold font-heading">{t('review.supersededTitle')}</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {t('review.supersededDescription')}
            </p>
          </div>

          {replacementReviewPath && (
            <Button
              variant="outline"
              onClick={() => navigate({ to: replacementReviewPath })}
            >
              {t('review.openReplacementReview')}
            </Button>
          )}

          {review.archivedSnapshot?.files.length ? (
            <div className="space-y-3">
              <Label className="text-xs text-muted-foreground uppercase tracking-wider">
                {t('review.archivedFileHashes')}
              </Label>
              <div className="divide-y divide-border/60 rounded-xl border border-border/70 bg-background/60">
                {review.archivedSnapshot.files.map((file) => (
                  <div key={file.path} className="space-y-1 px-4 py-3">
                    <p className="font-mono text-sm text-foreground">{file.path}</p>
                    <p className="break-all font-mono text-xs text-muted-foreground">
                      SHA-256 {file.sha256}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </Card>
      )}

      {review.status === 'PENDING' && (
        <Card className="p-8 space-y-6">
          <h2 className="text-xl font-bold font-heading">{t('review.actions')}</h2>

          <div className="space-y-3">
            <Label htmlFor="comment" className="text-sm font-semibold font-heading">{t('review.commentLabel')}</Label>
            <Textarea
              id="comment"
              placeholder={t('review.commentPlaceholder')}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={4}
            />
          </div>

          <div className="flex gap-3">
            <Button
              data-review-approve
              onClick={() => {
                if (isApprovalBlocked) {
                  return
                }
                if (isPartialScan) {
                  setScanOverrideDialog(true)
                } else {
                  setApproveDialog(true)
                }
              }}
              disabled={approveMutation.isPending || rejectMutation.isPending || isApprovalBlocked}
            >
              {t('review.approve')}
            </Button>
            {!showRejectForm ? (
              <Button
                variant="destructive"
                onClick={() => setShowRejectForm(true)}
                disabled={approveMutation.isPending || rejectMutation.isPending}
              >
                {t('review.reject')}
              </Button>
            ) : (
              <>
                <Button
                  variant="destructive"
                  onClick={() => {
                    if (!comment.trim()) {
                      toast.error(t('review.rejectReasonRequired'))
                      return
                    }
                    setRejectDialog(true)
                  }}
                  disabled={approveMutation.isPending || rejectMutation.isPending || !comment.trim()}
                >
                  {t('review.confirmReject')}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowRejectForm(false)}
                  disabled={approveMutation.isPending || rejectMutation.isPending}
                >
                  {t('review.cancelReject')}
                </Button>
              </>
            )}
          </div>

          {approvalBlockReason && (
            <p className="text-sm text-muted-foreground">{t(approvalBlockReason)}</p>
          )}

          {isPartialScan && canOverridePartialScan && (
            <p className="text-sm text-amber-700 dark:text-amber-300">{t('review.scanOverrideRequired')}</p>
          )}

          {showRejectForm && !comment.trim() && (
            <p className="text-sm text-destructive">{t('review.rejectReasonRequired')}</p>
          )}
        </Card>
      )}

      {!review.superseded && skillId && versionId ? (
        <SecurityAuditSection skillId={skillId} versionId={versionId} versionStatus={activeReviewVersion?.status} />
      ) : null}

      {!review.superseded && (
        <ReviewSkillDetailSection
          detail={reviewSkillDetail}
          isLoading={isLoadingReviewSkillDetail}
          hasError={Boolean(reviewSkillDetailError)}
          reviewId={taskId}
        />
      )}

      <ConfirmDialog
        open={approveDialog}
        onOpenChange={setApproveDialog}
        title={t('review.approveTitle')}
        description={t('review.approveDescription')}
        confirmText={t('review.approveConfirm')}
        onConfirm={handleApprove}
      />

      <ScanOverrideDialog
        open={scanOverrideDialog}
        isPending={approveMutation.isPending}
        onOpenChange={setScanOverrideDialog}
        onConfirm={handleScanOverrideApprove}
      />

      <ConfirmDialog
        open={rejectDialog}
        onOpenChange={setRejectDialog}
        title={t('review.rejectTitle')}
        description={t('review.rejectDescription')}
        confirmText={t('review.rejectConfirm')}
        variant="destructive"
        onConfirm={handleReject}
      />
      </div>

      {/* Sidebar — file browser for the review-bound active version */}
      <aside className="w-full lg:w-80 flex-shrink-0 space-y-5">
        {reviewFiles && reviewFiles.length > 0 && (
          <Card className="p-5 space-y-3">
            <button
              type="button"
              className="flex w-full items-center gap-2 text-left"
              aria-expanded={fileBrowserOpen}
              onClick={() => setFileBrowserOpen((v) => !v)}
            >
              <Folder className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-semibold font-heading text-foreground">
                {t('fileTree.title')}
              </span>
              <span className="text-xs text-muted-foreground ml-auto mr-2">
                {reviewFiles.length}
              </span>
              <span className={cn(
                'text-muted-foreground transition-transform duration-200',
                fileBrowserOpen && 'rotate-180'
              )}>
                <ChevronDown className="h-4 w-4" />
              </span>
            </button>
            {fileBrowserOpen && (
              <div className="max-h-[400px] overflow-y-auto -mx-5 px-5">
                <FileTree files={reviewFiles} onFileClick={handleFileClick} bare />
              </div>
            )}
          </Card>
        )}
        {reviewSkillDetail?.activeVersion && (
          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{t('review.activeReviewVersion')}</span>
              <span className="font-mono font-semibold text-foreground">v{reviewSkillDetail.activeVersion}</span>
            </div>
          </Card>
        )}
      </aside>

      {/* File preview dialog */}
      <FilePreviewDialog
        open={previewDialogOpen}
        onOpenChange={setPreviewDialogOpen}
        node={previewNode}
        content={previewContent || null}
        isLoading={isLoadingPreview}
        error={previewError}
        onDownload={handleDownloadFile}
      />
    </div>
  )
}

export function ReviewDetailPage() {
  const { id } = useParams({ from: '/dashboard/reviews/$id' })

  return (
    <ReviewDetailScreen
      taskId={Number(id)}
      backTo={buildGlobalReviewsPath()}
    />
  )
}

export function NamespaceReviewDetailPage() {
  const { id, slug } = useParams({ from: '/dashboard/namespaces/$slug/reviews/$id' })

  return (
    <ReviewDetailScreen
      taskId={Number(id)}
      backTo={buildNamespaceReviewsPath(slug)}
      namespaceSlug={slug}
    />
  )
}

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Label } from '@/shared/ui/label'
import { Textarea } from '@/shared/ui/textarea'

interface ScanOverrideDialogProps {
  open: boolean
  isPending: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (reason: string) => void | Promise<void>
}

export function ScanOverrideDialog({
  open,
  isPending,
  onOpenChange,
  onConfirm,
}: ScanOverrideDialogProps) {
  const { t } = useTranslation()
  const [acknowledged, setAcknowledged] = useState(false)
  const [reason, setReason] = useState('')
  const trimmedReason = reason.trim()

  const handleOpenChange = (nextOpen: boolean) => {
    if (isPending) {
      return
    }
    if (!nextOpen) {
      setAcknowledged(false)
      setReason('')
    }
    onOpenChange(nextOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('review.scanOverrideTitle')}</DialogTitle>
          <DialogDescription>{t('review.scanOverrideDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <Label className="flex cursor-pointer items-start gap-3 rounded-lg border border-amber-500/35 bg-amber-500/10 p-4 leading-5">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 shrink-0 accent-primary"
              checked={acknowledged}
              disabled={isPending}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            <span>{t('review.scanOverrideAcknowledge')}</span>
          </Label>

          <div className="space-y-2">
            <Label htmlFor="scan-override-reason">{t('review.scanOverrideReasonLabel')}</Label>
            <Textarea
              id="scan-override-reason"
              value={reason}
              disabled={isPending}
              placeholder={t('review.scanOverrideReasonPlaceholder')}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={isPending} onClick={() => handleOpenChange(false)}>
            {t('dialog.cancel')}
          </Button>
          <Button
            disabled={isPending || !acknowledged || !trimmedReason}
            onClick={() => void onConfirm(trimmedReason)}
          >
            {t('review.scanOverrideConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

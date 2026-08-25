import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/shared/ui/button'

interface InstallSelectionTrayProps {
  selectedCount: number
  maxSelected: number
  onClear: () => void
  onContinue: () => void
}

export function InstallSelectionTray({
  selectedCount,
  maxSelected,
  onClear,
  onContinue,
}: InstallSelectionTrayProps) {
  const { t } = useTranslation()

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 px-4 py-3 shadow-[0_-8px_24px_rgba(15,23,42,0.12)] backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p role="status" aria-live="polite" className="font-medium">
            {t('installSelection.count', { count: selectedCount, max: maxSelected })}
          </p>
          {selectedCount >= maxSelected && (
            <p className="text-sm text-muted-foreground">
              {t('installSelection.limitReached', { max: maxSelected })}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" onClick={onClear}>
            {t('installSelection.clear')}
          </Button>
          <Button type="button" disabled={selectedCount === 0} onClick={onContinue}>
            {t('installSelection.continue')}
            <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  )
}

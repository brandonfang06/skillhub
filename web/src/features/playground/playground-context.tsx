import * as Dialog from '@radix-ui/react-dialog'
import { FileText, Files, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'
import type { SidecarContextFile } from './api'


type PlaygroundContextProps = {
  files: SidecarContextFile[]
  selectedPath: string | null
  onSelectedPathChange: (path: string) => void
}

function ContextBrowser({
  files,
  selectedPath,
  onSelectedPathChange,
}: PlaygroundContextProps) {
  const { t } = useTranslation()
  const selectedFile =
    files.find((file) => file.path === selectedPath) ?? files[0]

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav
        aria-label={t('playground.contextFiles')}
        className="max-h-44 shrink-0 overflow-y-auto border-b border-[#25272D] p-2"
      >
        {files.length === 0 ? (
          <p className="px-2 py-3 text-xs text-[#858B96]">
            {t('playground.noContext')}
          </p>
        ) : (
          files.map((file) => {
            const selected = selectedFile?.path === file.path
            return (
              <button
                key={file.path}
                type="button"
                onClick={() => onSelectedPathChange(file.path)}
                aria-pressed={selected}
                className={cn(
                  'flex h-11 w-full items-center gap-2 rounded-md px-2 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 min-[900px]:h-9',
                  selected
                    ? 'bg-[#17181D] text-[#F7F8F8]'
                    : 'text-[#A4A9B3] hover:bg-[#17181D]/70 hover:text-[#F7F8F8]',
                )}
                title={file.path}
              >
                <FileText
                  className={cn(
                    'h-3.5 w-3.5 shrink-0',
                    selected ? 'text-indigo-400' : 'text-[#858B96]',
                  )}
                />
                <span className="truncate font-mono">{file.path}</span>
              </button>
            )
          })
        )}
      </nav>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {selectedFile ? (
          <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-5 text-[#D8DBE2]">
            {selectedFile.content}
          </pre>
        ) : (
          <p className="text-xs text-[#858B96]">
            {t('playground.noContext')}
          </p>
        )}
      </div>
    </div>
  )
}

export function PlaygroundContextPanel(props: PlaygroundContextProps) {
  const { t } = useTranslation()

  return (
    <aside
      data-playground-context-panel
      className="hidden min-h-0 min-w-0 flex-col border-r border-[#25272D] bg-[#0F1012] min-[900px]:order-first min-[900px]:flex"
    >
      <div className="flex h-12 shrink-0 items-center border-b border-[#25272D] px-3">
        <h2 className="text-sm font-semibold text-[#F7F8F8]">
          {t('playground.context')}
        </h2>
      </div>
      <ContextBrowser {...props} />
    </aside>
  )
}

export function PlaygroundContextDrawer(props: PlaygroundContextProps) {
  const { t } = useTranslation()

  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-11 w-11 text-[#A4A9B3] hover:bg-[#17181D] hover:text-[#F7F8F8] min-[900px]:hidden"
          aria-label={t('playground.openContext')}
          title={t('playground.openContext')}
        >
          <Files className="h-4 w-4" />
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 data-[state=open]:animate-fade-in motion-reduce:animate-none" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex h-dvh w-[min(100vw,26rem)] flex-col border-l border-[#343740] bg-[#0F1012] text-[#F7F8F8] shadow-2xl focus:outline-none">
          <div className="flex h-14 shrink-0 items-center justify-between border-b border-[#25272D] px-4">
            <Dialog.Title className="text-sm font-semibold">
              {t('playground.context')}
            </Dialog.Title>
            <Dialog.Description className="sr-only">
              {t('playground.contextDescription')}
            </Dialog.Description>
            <Dialog.Close asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-11 w-11 text-[#A4A9B3] hover:bg-[#17181D] hover:text-[#F7F8F8]"
                aria-label={t('playground.closeContext')}
                title={t('playground.closeContext')}
              >
                <X className="h-4 w-4" />
              </Button>
            </Dialog.Close>
          </div>
          <ContextBrowser {...props} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

import { useMemo, useState, type FormEvent, type KeyboardEvent } from 'react'
import {
  AlertCircle,
  Check,
  Copy,
  Loader2,
  RefreshCw,
  RotateCcw,
  Send,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  buildSkillhubInstallCommand,
  getBaseUrl,
} from '@/features/skill/install-command'
import { useCopyToClipboard } from '@/shared/lib/clipboard'
import { Button } from '@/shared/ui/button'
import { Textarea } from '@/shared/ui/textarea'
import type { ChatMessage, PlaygroundState } from './use-playground'


type PlaygroundChatProps = {
  state: PlaygroundState
  messages: ChatMessage[]
  isSending: boolean
  namespace: string
  slug: string
  errorCode?: string | null
  onSend: (content: string) => void
  onReset: () => void
  onReload?: () => void
}

export function PlaygroundChat({
  state,
  messages,
  isSending,
  namespace,
  slug,
  errorCode,
  onSend,
  onReset,
  onReload,
}: PlaygroundChatProps) {
  const { t } = useTranslation()
  const [prompt, setPrompt] = useState('')
  const [copied, copy] = useCopyToClipboard()
  const installCommand = useMemo(
    () => buildSkillhubInstallCommand(namespace, slug, getBaseUrl()),
    [namespace, slug],
  )
  const hasCompletedResponse = messages.some(
    (message) => message.role === 'assistant' && message.completed === true,
  )

  const submit = () => {
    const content = prompt.trim()
    if (!content || state !== 'ready' || isSending) {
      return
    }
    onSend(content)
    setPrompt('')
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    submit()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  const handleCopyInstall = async () => {
    try {
      await copy(installCommand)
    } catch (error) {
      console.error('Failed to copy install command:', error)
    }
  }

  const handleReload = () => {
    if (onReload) {
      onReload()
      return
    }
    window.location.reload()
  }

  return (
    <section
      data-playground-chat
      className="flex min-h-0 min-w-0 flex-col bg-[#09090B]"
    >
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-[#25272D] px-3 sm:px-4">
        <h2 className="text-sm font-semibold text-[#F7F8F8]">
          {t('playground.chat')}
        </h2>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onReset}
          disabled={state !== 'ready' || isSending || messages.length === 0}
          className="h-11 w-11 text-[#A4A9B3] hover:bg-[#17181D] hover:text-[#F7F8F8]"
          aria-label={t('playground.reset')}
          title={t('playground.reset')}
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </header>

      <div
        className="min-h-0 flex-1 space-y-5 overflow-y-auto px-3 py-5 sm:px-6"
        aria-live="polite"
      >
        {state === 'connecting' && (
          <div className="flex h-full min-h-48 items-center justify-center gap-2 text-sm text-[#A4A9B3]">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('playground.connectingTitle')}
          </div>
        )}
        {(state === 'unavailable' || state === 'expired') && (
          <div className="flex h-full min-h-48 flex-col items-center justify-center px-6 text-center">
            <AlertCircle className="mb-3 h-6 w-6 text-[#858B96]" />
            <h3 className="text-sm font-semibold text-[#F7F8F8]">
              {state === 'expired'
                ? t('playground.expiredTitle')
                : t('playground.unavailableTitle')}
            </h3>
            <p className="mt-2 max-w-md text-sm text-[#A4A9B3]">
              {state === 'expired'
                ? t('playground.expiredDescription')
                : t('playground.unavailableDescription')}
            </p>
            {state === 'expired' && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleReload}
                className="mt-4 h-11 border-[#343740] text-[#F7F8F8] hover:border-indigo-500/70 hover:bg-[#17181D]"
              >
                <RefreshCw className="mr-2 h-3.5 w-3.5" />
                {t('playground.reload')}
              </Button>
            )}
          </div>
        )}
        {state === 'ready' && messages.length === 0 && (
          <div className="flex h-full min-h-48 items-center justify-center text-sm text-[#858B96]">
            {t('playground.emptyState')}
          </div>
        )}
        {state === 'ready' && messages.map((message) => (
          <div
            key={message.id}
            className={
              message.role === 'user'
                ? 'ml-auto max-w-[85%] rounded-md bg-indigo-600 px-4 py-3 text-sm text-white sm:max-w-[75%]'
                : 'mr-auto max-w-[92%] border-l border-[#343740] px-4 py-2 text-sm text-[#E6E8EC] sm:max-w-[82%]'
            }
          >
            <div className="mb-1 text-xs font-medium text-current opacity-60">
              {message.role === 'user'
                ? t('playground.you')
                : t('playground.assistant')}
            </div>
            <div className="whitespace-pre-wrap break-words">
              {message.content}
              {message.streaming && (
                <span className="ml-1 inline-block h-3 w-1 animate-pulse bg-current" />
              )}
            </div>
          </div>
        ))}
      </div>

      {state === 'ready' && hasCompletedResponse && (
        <div
          data-playground-install-cta
          className="flex shrink-0 items-center gap-3 border-t border-[#25272D] bg-[#0F1012] px-3 py-2.5 sm:px-4"
        >
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-[#F7F8F8]">
              {t('playground.installReady')}
            </p>
            <code className="block truncate font-mono text-[11px] text-[#858B96]">
              {installCommand}
            </code>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleCopyInstall}
            className="h-11 w-11 shrink-0 border-[#343740] px-0 text-[#F7F8F8] hover:border-indigo-500/70 hover:bg-[#17181D] min-[900px]:h-8 min-[900px]:w-auto min-[900px]:px-3"
            aria-label={
              copied
                ? t('playground.installCommandCopied')
                : t('playground.copyInstallCommand')
            }
            title={
              copied
                ? t('playground.installCommandCopied')
                : t('playground.copyInstallCommand')
            }
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 min-[900px]:mr-2" />
            ) : (
              <Copy className="h-3.5 w-3.5 min-[900px]:mr-2" />
            )}
            <span className="hidden min-[900px]:inline">
              {copied
                ? t('playground.installCommandCopied')
                : t('playground.copyInstallCommand')}
            </span>
          </Button>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="shrink-0 border-t border-[#25272D] bg-[#0F1012] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4 sm:pt-4"
      >
        {errorCode && (
          <div
            role="alert"
            className="mb-3 flex items-center gap-2 text-sm text-red-400"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{t(`playground.errors.${errorCode}`)}</span>
          </div>
        )}
        <div className="flex items-end gap-2 rounded-lg border border-[#343740] bg-[#17181D] p-2 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/25">
          <Textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('playground.promptPlaceholder')}
            disabled={state !== 'ready' || isSending}
            className="min-h-16 max-h-36 resize-none border-0 bg-transparent px-2 py-2 text-[#F7F8F8] placeholder:text-[#858B96] focus-visible:border-transparent focus-visible:ring-0"
          />
          <Button
            type="submit"
            size="icon"
            disabled={state !== 'ready' || isSending || !prompt.trim()}
            className="h-11 w-11 shrink-0 rounded-md bg-indigo-600 text-white shadow-none hover:bg-indigo-500 hover:opacity-100"
            aria-label={t('playground.send')}
            title={t('playground.send')}
          >
            {isSending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </form>
    </section>
  )
}

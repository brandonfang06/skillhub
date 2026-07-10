import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { AlertCircle, Loader2, RotateCcw, Send } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/shared/ui/button'
import { Textarea } from '@/shared/ui/textarea'
import type { ChatMessage, PlaygroundState } from './use-playground'


type PlaygroundChatProps = {
  state: PlaygroundState
  messages: ChatMessage[]
  isSending: boolean
  onSend: (content: string) => void
  onReset: () => void
}

export function PlaygroundChat({
  state,
  messages,
  isSending,
  onSend,
  onReset,
}: PlaygroundChatProps) {
  const { t } = useTranslation()
  const [prompt, setPrompt] = useState('')

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

  return (
    <section className="flex min-h-[560px] min-w-0 flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <h2 className="text-sm font-semibold text-foreground">
          {t('playground.chat')}
        </h2>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onReset}
          disabled={state !== 'ready' || messages.length === 0}
          aria-label={t('playground.reset')}
          title={t('playground.reset')}
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </header>

      <div
        className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5"
        aria-live="polite"
      >
        {state === 'connecting' && (
          <div className="flex h-full min-h-64 items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('playground.connectingTitle')}
          </div>
        )}
        {(state === 'unavailable' || state === 'expired') && (
          <div className="flex h-full min-h-64 flex-col items-center justify-center px-6 text-center">
            <AlertCircle className="mb-3 h-6 w-6 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">
              {state === 'expired'
                ? t('playground.expiredTitle')
                : t('playground.unavailableTitle')}
            </h3>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              {state === 'expired'
                ? t('playground.expiredDescription')
                : t('playground.unavailableDescription')}
            </p>
          </div>
        )}
        {state === 'ready' && messages.length === 0 && (
          <div className="flex h-full min-h-64 items-center justify-center text-sm text-muted-foreground">
            {t('playground.emptyState')}
          </div>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={
              message.role === 'user'
                ? 'ml-auto max-w-[80%] rounded-md bg-primary px-4 py-3 text-sm text-primary-foreground'
                : 'mr-auto max-w-[88%] border-l-2 border-border px-4 py-2 text-sm text-foreground'
            }
          >
            <div className="mb-1 text-xs font-medium opacity-70">
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

      <form
        onSubmit={handleSubmit}
        className="shrink-0 border-t border-border p-4"
      >
        <div className="flex items-end gap-2">
          <Textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('playground.promptPlaceholder')}
            disabled={state !== 'ready'}
            className="min-h-20 max-h-40 resize-none"
          />
          <Button
            type="submit"
            size="icon"
            disabled={state !== 'ready' || isSending || !prompt.trim()}
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

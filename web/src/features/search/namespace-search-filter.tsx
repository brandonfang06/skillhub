import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Check, ChevronDown, Loader2, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import { cn } from '@/shared/lib/utils'
import { useSearchableNamespaces } from './use-searchable-namespaces'

interface NamespaceSearchFilterProps {
  value: string
  onValueChange: (value: string) => void
  className?: string
}

export function NamespaceSearchFilter({ value, onValueChange, className }: NamespaceSearchFilterProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const firstResultRef = useRef<HTMLDivElement>(null)
  const lastResultRef = useRef<HTMLDivElement>(null)
  const [selectedLabel, setSelectedLabel] = useState<{ slug: string; displayName: string } | null>(null)
  const { data = [], isFetching, isError, refetch } = useSearchableNamespaces(query, open)
  const selected = data.find((namespace) => namespace.slug === value)
  const displayName = selected?.displayName
    ?? (selectedLabel?.slug === value ? selectedLabel.displayName : undefined)

  useEffect(() => {
    const timeout = window.setTimeout(() => setQuery(input.trim()), 250)
    return () => window.clearTimeout(timeout)
  }, [input])

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) window.setTimeout(() => inputRef.current?.focus(), 0)
    else {
      setInput('')
      setQuery('')
    }
  }

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      firstResultRef.current?.focus()
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      lastResultRef.current?.focus()
      return
    }
    if (event.key !== 'Escape') event.stopPropagation()
  }

  return (
    <DropdownMenu open={open} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t('search.namespaceFilterLabel')}
          className={cn(
            'flex h-11 min-w-0 items-center justify-between gap-2 rounded-lg border border-border/60 bg-secondary/50 px-3 text-sm',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 sm:min-w-48',
            className,
          )}
        >
          <span className="truncate">{displayName ? `${displayName} (@${value})` : value ? `@${value}` : t('search.allNamespaces')}</span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[min(22rem,calc(100vw-2rem))] p-0">
        <div className="border-b border-border p-2">
          <div className="flex items-center gap-2 rounded-md border border-border bg-background px-3">
            <Search className="h-4 w-4 text-muted-foreground" />
            <input
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleInputKeyDown}
              aria-label={t('search.namespaceSearchLabel')}
              placeholder={t('search.namespaceSearchPlaceholder')}
              className="h-10 min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
            {isFetching ? <Loader2 aria-label={t('common.loading')} className="h-4 w-4 animate-spin" /> : null}
          </div>
        </div>
        <DropdownMenuItem onSelect={() => onValueChange('')} className="m-1">
          {t('search.allNamespaces')}
          {!value ? <Check className="ml-auto h-4 w-4" /> : null}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <div className="max-h-72 overflow-y-auto overscroll-contain p-1">
          {isError ? (
            <button type="button" onClick={() => refetch()} className="w-full px-3 py-5 text-sm text-destructive">
              {t('search.namespaceLoadError')}
            </button>
          ) : data.length ? data.map((namespace, index) => (
            <DropdownMenuItem
              key={namespace.slug}
              ref={(element) => {
                if (index === 0) firstResultRef.current = element
                if (index === data.length - 1) lastResultRef.current = element
              }}
              onSelect={() => {
                setSelectedLabel({ slug: namespace.slug, displayName: namespace.displayName })
                onValueChange(namespace.slug)
              }}
              className="gap-3 py-2"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{namespace.displayName}</span>
                <span className="block truncate text-xs text-muted-foreground">@{namespace.slug}</span>
              </span>
              <span className="text-xs text-muted-foreground">{namespace.visibleSkillCount}</span>
              {namespace.slug === value ? <Check className="h-4 w-4" /> : null}
            </DropdownMenuItem>
          )) : !isFetching ? (
            <p role="status" className="px-3 py-5 text-center text-sm text-muted-foreground">{t('search.noMatchingNamespaces')}</p>
          ) : null}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

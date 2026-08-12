import { useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Check, ChevronDown, Search, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ManagedNamespace } from '@/api/types'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import { SELECT_TRIGGER_CLASS_NAME } from '@/shared/ui/select'
import { cn } from '@/shared/lib/utils'

interface NamespacePickerProps {
  namespaces: ManagedNamespace[]
  value: string
  onValueChange: (value: string) => void
  labelId: string
}

function normalizeSearchTerm(value: string) {
  return value.trim().toLowerCase()
}

export function filterNamespaces(namespaces: ManagedNamespace[], query: string) {
  const normalizedQuery = normalizeSearchTerm(query)
  if (!normalizedQuery) {
    return namespaces
  }

  return namespaces.filter((namespace) => (
    normalizeSearchTerm(namespace.displayName).includes(normalizedQuery)
    || normalizeSearchTerm(namespace.slug).includes(normalizedQuery)
  ))
}

export function NamespacePicker({
  namespaces,
  value,
  onValueChange,
  labelId,
}: NamespacePickerProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const searchInputRef = useRef<HTMLInputElement>(null)
  const firstResultRef = useRef<HTMLDivElement>(null)
  const lastResultRef = useRef<HTMLDivElement>(null)
  const selectedNamespace = namespaces.find((namespace) => namespace.slug === value)
  const filteredNamespaces = useMemo(
    () => filterNamespaces(namespaces, query),
    [namespaces, query],
  )
  const selectedLabel = selectedNamespace
    ? `${selectedNamespace.displayName} (@${selectedNamespace.slug})`
    : value
      ? `@${value}`
      : t('publish.selectNamespace')

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) {
      window.setTimeout(() => searchInputRef.current?.focus(), 0)
    } else {
      setQuery('')
    }
  }

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
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

    if (event.key !== 'Escape') {
      event.stopPropagation()
    }
  }

  return (
    <DropdownMenu open={open} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <button
          id="namespace"
          type="button"
          aria-labelledby={labelId}
          className={cn(
            SELECT_TRIGGER_CLASS_NAME,
            !value && 'text-muted-foreground',
          )}
        >
          <span className="truncate text-left">{selectedLabel}</span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="w-[var(--radix-dropdown-menu-trigger-width)] max-w-[calc(100vw-2rem)] p-0"
      >
        <div className="border-b border-border p-2">
          <div className="flex items-center gap-2 rounded-md border border-border bg-background px-3 focus-within:ring-2 focus-within:ring-primary/40">
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
            <input
              ref={searchInputRef}
              type="search"
              role="searchbox"
              aria-label={t('publish.namespaceSearchLabel')}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder={t('publish.namespaceSearchPlaceholder')}
              className="h-10 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
        </div>

        <DropdownMenuItem
          disabled={!value}
          onSelect={() => onValueChange('')}
          className="m-1 gap-2 text-muted-foreground"
        >
          <X className="h-4 w-4 shrink-0" />
          {t('publish.clearNamespace')}
        </DropdownMenuItem>
        <DropdownMenuSeparator />

        <div className="max-h-80 overflow-y-auto overscroll-contain p-1">
          {filteredNamespaces.length > 0 ? filteredNamespaces.map((namespace, index) => (
            <DropdownMenuItem
              key={namespace.id}
              ref={(element) => {
                if (index === 0) {
                  firstResultRef.current = element
                }
                if (index === filteredNamespaces.length - 1) {
                  lastResultRef.current = element
                }
              }}
              onSelect={() => onValueChange(namespace.slug)}
              className="flex w-full justify-between gap-3 py-2"
            >
              <span className="min-w-0">
                <span className="block truncate font-medium">{namespace.displayName}</span>
                <span className="block truncate text-xs text-muted-foreground">@{namespace.slug}</span>
              </span>
              {namespace.slug === value && (
                <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              )}
            </DropdownMenuItem>
          )) : (
            <p role="status" className="px-3 py-6 text-center text-sm text-muted-foreground">
              {t('publish.noMatchingNamespace')}
            </p>
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

import { startTransition, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import type { SkillSummary } from '@/api/types'
import { useAuth } from '@/features/auth/use-auth'
import { SearchBar } from '@/features/search/search-bar'
import { NamespaceSearchFilter } from '@/features/search/namespace-search-filter'
import { SkillCard } from '@/features/skill/skill-card'
import { SkeletonList } from '@/shared/components/skeleton-loader'
import { EmptyState } from '@/shared/components/empty-state'
import { Pagination } from '@/shared/components/pagination'
import { useSearchSkills } from '@/shared/hooks/use-skill-queries'
import { useVisibleLabels } from '@/shared/hooks/use-label-queries'
import { useMyStars } from '@/shared/hooks/use-user-queries'
import { normalizeSearchQuery, parseNamespaceSearchInput } from '@/shared/lib/search-query'
import { Button } from '@/shared/ui/button'
import { APP_SHELL_PAGE_CLASS_NAME } from '@/app/page-shell-style'
import { buildReturnTo } from '@/shared/lib/auth-route'
import {
  installSelectionSkillCoordinate,
  MAX_SELECTED_SKILLS,
  useInstallSelectionStore,
} from '@/features/install-selection/install-selection-store'
import { InstallSelectionTray } from '@/features/install-selection/install-selection-tray'
import { cn } from '@/shared/lib/utils'

const PAGE_SIZE = 12

interface SearchRouteState {
  q: string
  namespace?: string
  label?: string
  sort: string
  page: number
  starredOnly: boolean
}

function buildSearchRouteState(state: SearchRouteState): SearchRouteState {
  return {
    q: state.q,
    ...(state.namespace ? { namespace: state.namespace } : {}),
    label: state.label,
    sort: state.sort,
    page: state.page,
    starredOnly: state.starredOnly,
  }
}

function blurActiveElement() {
  if (typeof document === 'undefined' || typeof HTMLElement === 'undefined') {
    return
  }

  if (document.activeElement instanceof HTMLElement) {
    document.activeElement.blur()
  }
}

function scrollToTopOnPageChange() {
  if (typeof window === 'undefined') {
    return () => {}
  }

  let secondFrame = 0
  const firstFrame = window.requestAnimationFrame(() => {
    window.scrollTo({ top: 0, behavior: 'auto' })
    secondFrame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: 'auto' })
    })
  })

  return () => {
    window.cancelAnimationFrame(firstFrame)
    if (secondFrame) {
      window.cancelAnimationFrame(secondFrame)
    }
  }
}

/**
 * Skill discovery page with synchronized URL state.
 *
 * Search text, sorting, pagination, and the starred-only filter are mirrored into router search
 * params so the page can be shared, restored, and revisited without losing state.
 */
function filterStarredSkills(skills: SkillSummary[], query: string, namespace: string): SkillSummary[] {
  const normalizedQuery = query.trim().toLowerCase()
  const normalizedNamespace = namespace.trim().toLowerCase()

  return skills.filter((skill) => {
    const matchesNamespace = !normalizedNamespace || skill.namespace.toLowerCase() === normalizedNamespace
    if (!matchesNamespace) {
      return false
    }
    if (!normalizedQuery) {
      return true
    }
    return [skill.displayName, skill.summary, skill.namespace, skill.slug]
      .filter(Boolean)
      .some((value) => value!.toLowerCase().includes(normalizedQuery))
  })
}

function sortStarredSkills(skills: SkillSummary[], sort: string): SkillSummary[] {
  const sorted = [...skills]
  if (sort === 'downloads') {
    return sorted.sort((left, right) => right.downloadCount - left.downloadCount)
  }
  if (sort === 'newest' || sort === 'relevance') {
    return sorted.sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime())
  }
  return sorted
}

export function SearchPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const searchParams = useSearch({ from: '/search' })
  const { isAuthenticated } = useAuth()
  const isSelectionMode = useInstallSelectionStore((state) => state.isSelectionMode)
  const selectedSkills = useInstallSelectionStore((state) => state.selectedSkills)
  const enterSelectionMode = useInstallSelectionStore((state) => state.enterSelectionMode)
  const addSelectedSkill = useInstallSelectionStore((state) => state.addSkill)
  const removeSelectedSkill = useInstallSelectionStore((state) => state.removeSkill)
  const clearSelection = useInstallSelectionStore((state) => state.clearSelection)

  const q = normalizeSearchQuery(searchParams.q || '')
  const namespace = (searchParams.namespace || '').replace(/^@/, '')
  const selectedLabel = searchParams.label || ''
  const sort = searchParams.sort || 'newest'
  const page = searchParams.page ?? 0
  const starredOnly = searchParams.starredOnly ?? false
  const [queryInput, setQueryInput] = useState(q)
  const previousPageRef = useRef(page)
  const selectionEntryButtonRef = useRef<HTMLButtonElement>(null)
  const focusSelectionEntryAfterClearRef = useRef(false)

  useEffect(() => {
    setQueryInput(q)
  }, [namespace, q])

  useEffect(() => {
    if (previousPageRef.current !== page) {
      blurActiveElement()
      const cleanupScroll = scrollToTopOnPageChange()

      previousPageRef.current = page
      return () => {
        cleanupScroll()
      }
    }

    previousPageRef.current = page
  }, [page])

  useEffect(() => {
    if (!isSelectionMode && focusSelectionEntryAfterClearRef.current) {
      focusSelectionEntryAfterClearRef.current = false
      selectionEntryButtonRef.current?.focus()
    }
  }, [isSelectionMode])

  const { data, isLoading, isFetching } = useSearchSkills({
    q,
    namespace: namespace || undefined,
    label: selectedLabel || undefined,
    sort,
    page,
    size: PAGE_SIZE,
    starredOnly,
  })
  const { data: labels } = useVisibleLabels()
  const {
    data: starredSkills,
    isLoading: isLoadingStarred,
    isFetching: isFetchingStarred,
  } = useMyStars(starredOnly && isAuthenticated)
  useEffect(() => {
    // Debounce URL updates while the user is typing so query state stays shareable without
    // triggering a navigation on every keystroke.
    const parsedInput = parseNamespaceSearchInput(queryInput)
    const inputHasNamespace = queryInput.trimStart().startsWith('@')
    const nextNamespace = inputHasNamespace ? parsedInput.namespace : namespace
    if (parsedInput.query === q && nextNamespace === namespace) {
      return
    }

    if (!parsedInput.query && !nextNamespace) {
      startTransition(() => {
        navigate({ to: '/search', search: buildSearchRouteState({ q: '', label: selectedLabel, sort, page: 0, starredOnly }), replace: page === 0 })
      })
      return
    }

    const timeoutId = window.setTimeout(() => {
      startTransition(() => {
        navigate({ to: '/search', search: buildSearchRouteState({ q: parsedInput.query, namespace: nextNamespace, label: selectedLabel, sort, page: 0, starredOnly }), replace: true })
      })
    }, 250)

    return () => window.clearTimeout(timeoutId)
  }, [navigate, namespace, page, q, queryInput, selectedLabel, sort, starredOnly])

  const handleSearch = (query: string) => {
    const parsedInput = parseNamespaceSearchInput(query)
    const nextNamespace = query.trimStart().startsWith('@') ? parsedInput.namespace : namespace
    setQueryInput(query)
    startTransition(() => {
      navigate({ to: '/search', search: buildSearchRouteState({ q: parsedInput.query, namespace: nextNamespace, label: selectedLabel, sort, page: 0, starredOnly }), replace: true })
    })
  }

  const handleSortChange = (newSort: string) => {
    navigate({ to: '/search', search: buildSearchRouteState({ q, namespace, label: selectedLabel, sort: newSort, page: 0, starredOnly }) })
  }

  const handlePageChange = (newPage: number) => {
    blurActiveElement()
    navigate({ to: '/search', search: buildSearchRouteState({ q, namespace, label: selectedLabel, sort, page: newPage, starredOnly }) })
  }

  const handleLabelToggle = (label: string) => {
    const nextLabel = selectedLabel === label ? '' : label
    navigate({ to: '/search', search: buildSearchRouteState({ q, namespace, label: nextLabel, sort, page: 0, starredOnly }) })
  }

  const handleNamespaceClear = () => {
    navigate({ to: '/search', search: buildSearchRouteState({ q, label: selectedLabel, sort, page: 0, starredOnly }) })
  }

  const handleNamespaceChange = (nextNamespace: string) => {
    navigate({
      to: '/search',
      search: buildSearchRouteState({ q, namespace: nextNamespace, label: selectedLabel, sort, page: 0, starredOnly }),
    })
  }

  const redirectToLogin = () => navigate({
    to: '/login',
    search: {
      returnTo: buildReturnTo({
        pathname: window.location.pathname,
        searchStr: window.location.search,
        hash: window.location.hash,
      }),
    },
  })

  const handleStarredToggle = () => {
    if (!isAuthenticated) {
      redirectToLogin()
      return
    }

    navigate({ to: '/search', search: buildSearchRouteState({ q, namespace, label: selectedLabel, sort, page: 0, starredOnly: !starredOnly }) })
  }

  const handleStartSelection = () => {
    if (!isAuthenticated) {
      redirectToLogin()
      return
    }

    enterSelectionMode()
  }

  const handleClearSelection = () => {
    focusSelectionEntryAfterClearRef.current = true
    clearSelection()
  }

  const handleSkillClick = (namespace: string, slug: string) => {
    navigate({
      to: `/space/${namespace}/${encodeURIComponent(slug)}`,
      search: {
        returnTo: buildReturnTo({
          pathname: window.location.pathname,
          searchStr: window.location.search,
        }),
      },
    })
  }

  const filteredStarredSkills = starredOnly
    ? sortStarredSkills(filterStarredSkills(starredSkills ?? [], q, namespace), sort)
    : []
  const starredPageItems = starredOnly
    ? filteredStarredSkills.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
    : []
  const totalPages = starredOnly
    ? Math.ceil(filteredStarredSkills.length / PAGE_SIZE)
    : data
      ? Math.ceil(data.total / data.size)
      : 0
  const displayItems = starredOnly ? starredPageItems : (data?.items ?? [])
  const isPageLoading = starredOnly ? isLoadingStarred : isLoading
  const isUpdatingResults = starredOnly ? isFetchingStarred && !isLoadingStarred : isFetching && !isLoading
  const resultCount = starredOnly ? filteredStarredSkills.length : (data?.total ?? 0)

  return (
    <div className={cn(APP_SHELL_PAGE_CLASS_NAME)}>
      {/* Search Bar */}
      <div className="max-w-3xl mx-auto">
        <SearchBar
          value={queryInput}
          isSearching={isUpdatingResults}
          onChange={setQueryInput}
          onSearch={handleSearch}
          leadingControl={<NamespaceSearchFilter value={namespace} onValueChange={handleNamespaceChange} />}
        />
      </div>

      {/* Sort And Filters */}
      <div className="space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-muted-foreground">{t('search.sort.label')}</span>
            <div className="flex gap-2">
              <Button
                variant={sort === 'relevance' ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleSortChange('relevance')}
              >
                {t('search.sort.relevance')}
              </Button>
              <Button
                variant={sort === 'downloads' ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleSortChange('downloads')}
              >
                {t('search.sort.downloads')}
              </Button>
              <Button
                variant={sort === 'newest' ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleSortChange('newest')}
              >
                {t('search.sort.newest')}
              </Button>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {resultCount > 0 && (
              <div className="text-sm text-muted-foreground">
                {t('search.results', { count: resultCount })}
              </div>
            )}
            {!isSelectionMode && (
              <Button
                ref={selectionEntryButtonRef}
                type="button"
                variant="outline"
                size="sm"
                onClick={handleStartSelection}
              >
                {t('installSelection.start')}
              </Button>
            )}
          </div>
        </div>

        {isUpdatingResults ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{t('search.loadingMore')}</span>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <span className="shrink-0 text-sm font-medium text-muted-foreground">{t('search.filters.label')}</span>
          <Button
            variant={starredOnly ? 'default' : 'outline'}
            size="sm"
            onClick={handleStarredToggle}
          >
            {t('search.filterStarred')}
          </Button>
          {!starredOnly && labels?.map((label) => (
            <Button
              key={label.slug}
              variant={selectedLabel === label.slug ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleLabelToggle(label.slug)}
            >
              {label.displayName}
            </Button>
          ))}
          {namespace ? (
            <Button
              variant="default"
              size="sm"
              onClick={handleNamespaceClear}
            >
              {t('search.namespaceFilter', { namespace })}
            </Button>
          ) : null}
        </div>
      </div>

      {isSelectionMode && (
        <InstallSelectionTray
          selectedCount={selectedSkills.length}
          maxSelected={MAX_SELECTED_SKILLS}
          onClear={handleClearSelection}
          onContinue={() => navigate({ to: '/install' })}
        />
      )}

      {/* Results */}
      {isPageLoading ? (
        <SkeletonList count={PAGE_SIZE} />
      ) : displayItems.length > 0 ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {displayItems.map((skill, idx) => {
              const selected = selectedSkills.some((item) => (
                installSelectionSkillCoordinate(item) === installSelectionSkillCoordinate(skill)
              ))
              return (
                <div key={skill.id} className={`h-full animate-fade-up delay-${Math.min(idx % 6 + 1, 6)}`}>
                  <SkillCard
                    skill={skill}
                    highlightStarred
                    selectionMode={isSelectionMode}
                    selected={selected}
                    selectionDisabled={!selected && selectedSkills.length >= MAX_SELECTED_SKILLS}
                    onSelectionChange={(nextSelected) => {
                      const selectionSkill = {
                        id: skill.id,
                        namespace: skill.namespace,
                        slug: skill.slug,
                        displayName: skill.displayName,
                      }
                      if (nextSelected) {
                        addSelectedSkill(selectionSkill)
                      } else {
                        removeSelectedSkill(selectionSkill)
                      }
                    }}
                    onClick={() => handleSkillClick(skill.namespace, skill.slug)}
                  />
                </div>
              )
            })}
          </div>
          {totalPages > 1 && (
            <Pagination
              page={page}
              totalPages={totalPages}
              onPageChange={handlePageChange}
            />
          )}
        </>
      ) : (
        <EmptyState
          title={starredOnly ? t('search.noStarredResults') : t('search.noResults')}
          description={
            starredOnly
              ? (q ? t('search.noStarredResultsFor', { q }) : t('search.noStarredSkills'))
              : (q ? t('search.noResultsFor', { q }) : undefined)
          }
        />
      )}
    </div>
  )
}

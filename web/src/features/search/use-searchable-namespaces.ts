import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { searchApi } from '@/api/client'
import { useAuth } from '@/features/auth/use-auth'

export function useSearchableNamespaces(query: string, enabled = true) {
  const { user, isLoading } = useAuth()
  const normalizedQuery = query.trim()
  return useQuery({
    queryKey: ['search', 'namespaces', user?.userId ?? 'anonymous', normalizedQuery],
    queryFn: () => searchApi.listNamespaces({ q: normalizedQuery || undefined, limit: 20 }),
    enabled: enabled && !isLoading,
    placeholderData: keepPreviousData,
  })
}

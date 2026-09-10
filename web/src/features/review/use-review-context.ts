import { useQuery } from '@tanstack/react-query'
import { fetchJson } from '@/api/client'
import type { components } from '@/api/generated/review-context'

export type VersionReviewContext = components['schemas']['VersionReviewContext']

export function useReviewContext(skillId: number, version: string, userId: string | undefined, page: number, expanded: boolean) {
  return useQuery({
    queryKey: ['reviews', 'context', userId, skillId, version, page],
    queryFn: () => fetchJson<VersionReviewContext>(`/api/web/reviews/skills/${skillId}/versions/${encodeURIComponent(version)}/context?page=${page}&size=5`),
    enabled: !!userId && expanded,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: expanded ? 30_000 : false,
  })
}

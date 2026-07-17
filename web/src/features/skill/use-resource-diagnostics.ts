import { useQuery } from '@tanstack/react-query'
import { adminApi } from '@/api/client'

export function useResourceDiagnostics(skillId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'skills', skillId, 'resource-diagnostics'],
    queryFn: () => adminApi.getSkillResourceDiagnostics(skillId),
    enabled: enabled && skillId > 0,
  })
}

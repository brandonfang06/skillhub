import { redirect } from '@tanstack/react-router'
import { toAppRelativePath } from './runtime-config'

export type RouteLocationLike = {
  pathname: string
  searchStr?: string
  hash?: string
}

export function buildReturnTo(location: RouteLocationLike) {
  const target = `${location.pathname}${location.searchStr ?? ''}${location.hash ?? ''}`
  return toAppRelativePath(target) ?? target
}

export function createRequireAuth(getCurrentUser: () => Promise<unknown>) {
  return async function requireAuth({ location }: { location: RouteLocationLike }) {
    const user = await getCurrentUser()
    if (!user) {
      throw redirect({
        to: '/login',
        search: { returnTo: buildReturnTo(location) },
      })
    }
    return { user }
  }
}

export const PORTAL_ROOT_ID = 'skillhub-portals'

export function getPortalContainer(): HTMLElement | undefined {
  if (typeof document === 'undefined') {
    return undefined
  }
  return document.getElementById(PORTAL_ROOT_ID) ?? undefined
}

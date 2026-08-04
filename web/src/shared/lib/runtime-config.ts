export type RuntimeConfig = {
  apiBaseUrl?: string
  appBaseUrl?: string
  basePath?: string
  cliRegistryUrl?: string
  authDirectEnabled?: string
  authDirectProvider?: string
  localRegistrationEnabled?: string
  authSessionBootstrapEnabled?: string
  authSessionBootstrapProvider?: string
  authSessionBootstrapAuto?: string
  playgroundEnabled?: string
  playgroundBaseUrl?: string
}

declare global {
  interface Window {
    __SKILLHUB_RUNTIME_CONFIG__?: RuntimeConfig
  }
}

export function getRuntimeConfig(): RuntimeConfig {
  if (typeof window === 'undefined') {
    return {}
  }
  return window.__SKILLHUB_RUNTIME_CONFIG__ ?? {}
}

export function normalizeBasePath(value: string | undefined): string {
  const normalized = value?.trim() ?? ''
  if (normalized === '' || normalized === '/') {
    return ''
  }
  if (
    !normalized.startsWith('/')
    || normalized.startsWith('//')
    || normalized.includes('?')
    || normalized.includes('#')
    || normalized.includes('\\')
    || normalized.endsWith('//')
    || !/^\/[A-Za-z0-9._~/-]+$/.test(normalized)
  ) {
    throw new Error('Invalid SkillHub web base path')
  }

  const withoutTrailingSlash = normalized.replace(/\/+$/, '')
  const segments = withoutTrailingSlash.slice(1).split('/')
  if (segments.some((segment) => segment === '' || segment === '.' || segment === '..')) {
    throw new Error('Invalid SkillHub web base path')
  }
  return withoutTrailingSlash
}

export function getAppBasePath(): string {
  return normalizeBasePath(getRuntimeConfig().basePath)
}

export function getApiBaseUrl(): string {
  const configured = getRuntimeConfig().apiBaseUrl?.trim()
  if (configured) {
    return trimTrailingSlash(configured)
  }
  return getAppBasePath()
}

export function getPublicAppUrl(): string {
  return trimTrailingSlash(getRuntimeConfig().appBaseUrl?.trim() ?? '')
}

export function getBrowserAppUrl(): string {
  const configuredUrl = getPublicAppUrl()
  if (configuredUrl && !configuredUrl.includes('localhost')) {
    return configuredUrl
  }
  if (typeof window === 'undefined') {
    return ''
  }
  const origin = window.location.origin
    || `${window.location.protocol}//${window.location.host}`
  return `${trimTrailingSlash(origin)}${getAppBasePath()}`
}

export function getCliRegistryUrl(): string {
  const fallbackUrl = getBrowserAppUrl()
  const configuredUrl = getRuntimeConfig().cliRegistryUrl?.trim()
  if (!configuredUrl) {
    return fallbackUrl
  }

  try {
    const parsedUrl = new URL(configuredUrl)
    if (
      (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:')
      || parsedUrl.username
      || parsedUrl.password
      || parsedUrl.search
      || parsedUrl.hash
      || !/^\/[A-Za-z0-9._~/-]*$/.test(parsedUrl.pathname)
    ) {
      return fallbackUrl
    }
    return parsedUrl.toString().replace(/\/+$/, '')
  } catch {
    return fallbackUrl
  }
}

export function buildAppPath(path: string): string {
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new Error('SkillHub application paths must be root-relative')
  }
  return `${getAppBasePath()}${path}`
}

export function toAppRelativePath(path: string): string | undefined {
  if (!path.startsWith('/') || path.startsWith('//')) {
    return undefined
  }

  const suffixIndex = path.search(/[?#]/)
  const pathname = suffixIndex === -1 ? path : path.slice(0, suffixIndex)
  const suffix = suffixIndex === -1 ? '' : path.slice(suffixIndex)
  const basePath = getAppBasePath()

  if (!basePath) {
    return path
  }
  if (pathname === basePath) {
    return `/${suffix}`
  }
  if (!pathname.startsWith(`${basePath}/`)) {
    return undefined
  }
  return `${pathname.slice(basePath.length)}${suffix}`
}

function trimTrailingSlash(value: string): string {
  return value.length > 1 ? value.replace(/\/+$/, '') : value
}

import { CliError } from '../shared/errors'
import { EXIT } from '../shared/constants'

export interface WhoAmIResponse {
  handle: string
  displayName: string
  email?: string
}

export interface SearchItem {
  namespace: string
  slug: string
  latestVersion: string
  summary: string
}

export interface SearchResponse {
  items: SearchItem[]
  total: number
  limit: number
}

export interface ResolveResponse {
  namespace: string
  slug: string
  version: string
  versionId: number
  fingerprint: string
  downloadUrl: string
}

export interface DeleteResponse {
  ok: boolean
  scope: string
  action: string
  namespace: string
  slug: string
}

export interface PublishResponse {
  namespace: string
  slug: string
  version: string
  visibility: string
}

export interface DryRunResponse {
  valid: boolean
  errors: string[]
  warnings: string[]
  resolvedSlug: string | null
  resolvedVersion: string | null
}

interface PublicErrorFields {
  msg?: string
  requestId?: string
}

type ErrorResponseKind = 'json' | 'download'

export class SkillHubClient {
  constructor(
    readonly registry: string,
    readonly token?: string,
    private readonly fetchImpl: typeof fetch = fetch
  ) {}

  async whoami(): Promise<WhoAmIResponse> {
    return this.getJson('/auth/whoami')
  }

  async search(query: string, limit: number): Promise<SearchResponse> {
    const params = new URLSearchParams({ q: query, limit: String(limit) })
    return this.getJson(`/skills/search?${params}`)
  }

  async resolve(namespace: string, slug: string, version?: string): Promise<ResolveResponse> {
    const params = version ? `?version=${encodeURIComponent(version)}` : ''
    return this.getJson(`/skills/${namespace}/${slug}/resolve${params}`)
  }

  async downloadUrl(namespace: string, slug: string, version?: string): Promise<string> {
    if (version) {
      return `${this.registry}/api/cli/v1/skills/${namespace}/${slug}/versions/${version}/download`
    }
    return `${this.registry}/api/cli/v1/skills/${namespace}/${slug}/download`
  }

  async download(namespace: string, slug: string, version?: string): Promise<Response> {
    const url = await this.downloadUrl(namespace, slug, version)
    let response: Response
    try {
      response = await this.fetchImpl(url, { headers: this.headers() })
    } catch {
      throw new CliError('registry unreachable', EXIT.network, { registry: this.registry, next: 'check network or pass --registry' })
    }
    if (!response.ok) {
      throw await this.createResponseError(response, 'download')
    }
    return response
  }

  async deleteRemote(namespace: string, slug: string): Promise<DeleteResponse> {
    return this.deleteJson(`/skills/${namespace}/${slug}`)
  }

  async publish(namespace: string, file: Blob, visibility: string, fileName = 'skill.zip'): Promise<PublishResponse> {
    const formData = new FormData()
    formData.append('file', file, fileName)
    formData.append('visibility', visibility)
    let response: Response
    try {
      response = await this.fetchImpl(`${this.registry}/api/cli/v1/skills/${namespace}/publish`, {
        method: 'POST',
        headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
        body: formData
      })
    } catch {
      throw new CliError('registry unreachable', EXIT.network, { registry: this.registry, next: 'check network or pass --registry' })
    }
    return this.handleJsonResponse<PublishResponse>(response)
  }

  async validatePublish(namespace: string, file: Blob, visibility: string, fileName = 'skill.zip'): Promise<DryRunResponse> {
    const formData = new FormData()
    formData.append('file', file, fileName)
    formData.append('visibility', visibility)
    let response: Response
    try {
      response = await this.fetchImpl(`${this.registry}/api/cli/v1/skills/${namespace}/publish/validate`, {
        method: 'POST',
        headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
        body: formData
      })
    } catch {
      throw new CliError('registry unreachable', EXIT.network, { registry: this.registry, next: 'check network or pass --registry' })
    }
    return this.handleJsonResponse<DryRunResponse>(response)
  }

  private async getJson<T>(path: string): Promise<T> {
    let response: Response
    try {
      response = await this.fetchImpl(`${this.registry}/api/cli/v1${path}`, {
        headers: this.headers()
      })
    } catch (err) {
      throw new CliError('registry unreachable', EXIT.network, { registry: this.registry, next: 'check network or pass --registry' })
    }
    return this.handleJsonResponse<T>(response)
  }

  private async handleJsonResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      throw await this.createResponseError(response, 'json')
    }
    const body = await response.json()
    return body.data as T
  }

  private async createResponseError(response: Response, kind: ErrorResponseKind): Promise<CliError> {
    const publicFields = await this.readPublicErrorFields(response)
    const details: Record<string, unknown> = { registry: this.registry }
    if (publicFields.requestId) {
      details.requestId = publicFields.requestId
    }

    let fallback: string
    let exitCode: number = EXIT.generic
    if (response.status === 401) {
      fallback = 'authentication failed'
      exitCode = EXIT.auth
      details.next = 'run `skillhub login`'
    } else if (response.status === 403) {
      fallback = 'access denied'
      exitCode = EXIT.auth
    } else if (response.status === 404) {
      fallback = kind === 'download' ? 'skill or version not found' : 'resource not found'
    } else if (response.status === 502 || response.status === 503) {
      fallback = kind === 'download'
        ? `download failed with status ${response.status}`
        : `registry returned ${response.status}`
      exitCode = EXIT.network
    } else {
      fallback = kind === 'download'
        ? `download failed with status ${response.status}`
        : `registry returned ${response.status}`
    }
    return new CliError(publicFields.msg ?? fallback, exitCode, details)
  }

  private async readPublicErrorFields(response: Response): Promise<PublicErrorFields> {
    let body: unknown
    try {
      body = await response.json()
    } catch {
      return {}
    }
    if (typeof body !== 'object' || body === null || Array.isArray(body)) {
      return {}
    }
    const record = body as Record<string, unknown>
    const msg = typeof record.msg === 'string' ? record.msg.trim() : ''
    const requestId = typeof record.requestId === 'string' ? record.requestId.trim() : ''
    return {
      ...(msg ? { msg } : {}),
      ...(requestId ? { requestId } : {})
    }
  }

  private headers(): HeadersInit {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {}
  }

  private async deleteJson<T>(path: string): Promise<T> {
    let response: Response
    try {
      response = await this.fetchImpl(`${this.registry}/api/cli/v1${path}`, {
        method: 'DELETE',
        headers: this.headers()
      })
    } catch {
      throw new CliError('registry unreachable', EXIT.network, { registry: this.registry, next: 'check network or pass --registry' })
    }
    return this.handleJsonResponse<T>(response)
  }
}

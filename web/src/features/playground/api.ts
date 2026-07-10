export type SidecarSkill = {
  namespace: string
  slug: string
  displayName: string
  version: string
}

export type SidecarContextFile = {
  path: string
  content: string
}

export type SidecarSession = {
  sessionId: string
  modelKey: string
  skill: SidecarSkill
  contextFiles: SidecarContextFile[]
}

export class SidecarError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code)
  }
}

async function sidecarRequest(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new SidecarError(0, 'sidecar_unavailable')
  }
  if (!response.ok) {
    let code = `sidecar_${response.status}`
    try {
      const body = (await response.json()) as { detail?: string }
      code = body.detail || code
    } catch {
      // Keep the status-derived code when the provider returns no JSON body.
    }
    throw new SidecarError(response.status, code)
  }
  return response
}

async function sidecarJson<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await sidecarRequest(url, init)
  return response.json() as Promise<T>
}

export function createSidecarSession(
  baseUrl: string,
  capability: string,
): Promise<SidecarSession> {
  return sidecarJson(`${baseUrl}/v1/playground/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      productId: 'skillhub',
      source: { provider: 'skillhub', accessToken: capability },
    }),
  })
}

export function sendSidecarMessage(
  baseUrl: string,
  sessionId: string,
  content: string,
): Promise<{ accepted: boolean }> {
  return sidecarJson(
    `${sessionUrl(baseUrl, sessionId)}/messages`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    },
  )
}

export async function resetSidecarSession(
  baseUrl: string,
  sessionId: string,
): Promise<void> {
  await sidecarRequest(`${sessionUrl(baseUrl, sessionId)}/reset`, {
    method: 'POST',
  })
}

export async function deleteSidecarSession(
  baseUrl: string,
  sessionId: string,
): Promise<void> {
  await sidecarRequest(sessionUrl(baseUrl, sessionId), {
    method: 'DELETE',
  })
}

export function sidecarEventsUrl(
  baseUrl: string,
  sessionId: string,
): string {
  return `${sessionUrl(baseUrl, sessionId)}/events`
}

function sessionUrl(baseUrl: string, sessionId: string): string {
  return `${baseUrl}/v1/playground/sessions/${encodeURIComponent(sessionId)}`
}

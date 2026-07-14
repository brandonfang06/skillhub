import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createSidecarSession,
  deleteSidecarSession,
  resetSidecarSession,
  sendSidecarMessage,
  sidecarEventsUrl,
} from './api'


afterEach(() => vi.unstubAllGlobals())

describe('playground sidecar client', () => {
  it('creates a session without leaking the capability into the URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          sessionId: 'session-1',
          modelKey: 'primary',
          skill: {
            namespace: 'global',
            slug: 'notes',
            displayName: 'Notes',
            version: '1.0.0',
          },
          contextFiles: [
            {
              path: 'SKILL.md',
              content: 'Summarize',
              includedInPrompt: true,
            },
          ],
        }),
        {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const session = await createSidecarSession(
      'http://localhost:8091',
      'capability',
    )

    expect(session.contextFiles[0].path).toBe('SKILL.md')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8091/v1/playground/sessions',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('capability')
    expect(fetchMock.mock.calls[0][1].body).toContain(
      '"accessToken":"capability"',
    )
  })

  it('posts messages and session lifecycle commands to scoped endpoints', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ accepted: true }), {
          status: 202,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await sendSidecarMessage(
      'http://localhost:8091',
      'session-1',
      'hello',
    )
    await resetSidecarSession('http://localhost:8091', 'session-1')
    await deleteSidecarSession('http://localhost:8091', 'session-1')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'http://localhost:8091/v1/playground/sessions/session-1/messages',
      'http://localhost:8091/v1/playground/sessions/session-1/reset',
      'http://localhost:8091/v1/playground/sessions/session-1',
    ])
  })

  it('builds the EventSource URL from the opaque session id', () => {
    expect(sidecarEventsUrl('http://localhost:8091', 'session / 1')).toBe(
      'http://localhost:8091/v1/playground/sessions/session%20%2F%201/events',
    )
  })
})

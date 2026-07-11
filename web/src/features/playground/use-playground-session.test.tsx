// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'


const mocks = vi.hoisted(() => ({
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  resetSession: vi.fn(),
  sendMessage: vi.fn(),
  createCapability: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  getPlaygroundRuntimeConfig: () => ({
    enabled: true,
    baseUrl: 'http://sidecar.test',
  }),
  playgroundCapabilityApi: { create: mocks.createCapability },
}))

vi.mock('./api', () => {
  class SidecarError extends Error {
    constructor(
      readonly status: number,
      readonly code: string,
    ) {
      super(code)
    }
  }

  return {
    createSidecarSession: mocks.createSession,
    deleteSidecarSession: mocks.deleteSession,
    resetSidecarSession: mocks.resetSession,
    sendSidecarMessage: mocks.sendMessage,
    SidecarError,
    sidecarEventsUrl: (_baseUrl: string, sessionId: string) =>
      `http://sidecar.test/v1/playground/sessions/${sessionId}/events`,
  }
})

type Listener = (event: MessageEvent<string>) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []

  onopen: (() => void) | null = null
  private readonly listeners = new Map<string, Listener[]>()

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: EventListener) {
    const listeners = this.listeners.get(type) ?? []
    listeners.push(listener as Listener)
    this.listeners.set(type, listeners)
  }

  emit(type: string, payload: object) {
    const event = { data: JSON.stringify(payload) } as MessageEvent<string>
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event)
    }
  }

  close() {}
}

import { SidecarError } from './api'
import { usePlayground } from './use-playground'


function renderPlayground() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return renderHook(
    () =>
      usePlayground({
        namespace: 'global',
        slug: 'notes',
        version: '1.0.0',
      }),
    { wrapper },
  )
}

async function openSession(
  result: ReturnType<typeof renderPlayground>['result'],
) {
  await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
  act(() => FakeEventSource.instances[0].onopen?.())
  await waitFor(() => expect(result.current.state).toBe('ready'))
}


describe('usePlayground generation state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    mocks.createCapability.mockResolvedValue({ token: 'capability' })
    mocks.createSession.mockResolvedValue({
      sessionId: 'session-1',
      modelKey: 'default',
      skill: {
        namespace: 'global',
        slug: 'notes',
        displayName: 'Notes',
        version: '1.0.0',
      },
      contextFiles: [],
    })
    mocks.sendMessage.mockResolvedValue({ accepted: true })
    mocks.deleteSession.mockResolvedValue(undefined)
    mocks.resetSession.mockResolvedValue(undefined)
  })

  it('stays busy after HTTP acceptance until the completion event arrives', async () => {
    const { result } = renderPlayground()
    await openSession(result)

    act(() => result.current.send('Summarize this skill'))
    await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledOnce())
    await act(async () => {})

    expect(result.current.isSending).toBe(true)

    act(() =>
      FakeEventSource.instances[0].emit('message.completed', {
        type: 'message.completed',
      }),
    )
    await waitFor(() => expect(result.current.isSending).toBe(false))
  })

  it('keeps message limit errors recoverable in the current session', async () => {
    mocks.sendMessage.mockRejectedValueOnce(
      new SidecarError(409, 'message_limit_reached'),
    )
    const { result } = renderPlayground()
    await openSession(result)

    act(() => result.current.send('One more question'))

    await waitFor(() => expect(result.current.isSending).toBe(false))
    expect(result.current.state).toBe('ready')
    expect((result.current as { errorCode?: string }).errorCode).toBe(
      'message_limit_reached',
    )
  })

  it('keeps provider failures local and finalizes the streaming message', async () => {
    const { result } = renderPlayground()
    await openSession(result)
    act(() => result.current.send('Try the model'))
    await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledOnce())

    act(() => {
      FakeEventSource.instances[0].emit('message.started', {
        type: 'message.started',
      })
      FakeEventSource.instances[0].emit('error', {
        type: 'error',
        code: 'provider_unavailable',
      })
    })

    await waitFor(() => expect(result.current.isSending).toBe(false))
    expect(result.current.state).toBe('ready')
    expect((result.current as { errorCode?: string }).errorCode).toBe(
      'provider_unavailable',
    )
    expect(
      result.current.messages[result.current.messages.length - 1]?.streaming,
    ).toBe(false)
  })
})

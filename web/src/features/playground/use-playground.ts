import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import {
  getPlaygroundRuntimeConfig,
  playgroundCapabilityApi,
} from '@/api/client'
import {
  createSidecarSession,
  deleteSidecarSession,
  resetSidecarSession,
  sendSidecarMessage,
  SidecarError,
  sidecarEventsUrl,
  type SidecarSession,
} from './api'


export type PlaygroundState =
  | 'connecting'
  | 'ready'
  | 'unavailable'
  | 'expired'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export type PlaygroundEvent =
  | { type: 'message.started' }
  | { type: 'message.delta'; delta: string }
  | { type: 'message.completed' }
  | { type: 'session.reset' }
  | { type: 'error'; code: string }

type UsePlaygroundInput = {
  namespace: string
  slug: string
  version?: string
  enabled?: boolean
}

let messageSequence = 0

function nextMessageId(role: ChatMessage['role']): string {
  messageSequence += 1
  return `${role}-${messageSequence}`
}

export function applyPlaygroundEvent(
  messages: ChatMessage[],
  event: PlaygroundEvent,
): ChatMessage[] {
  if (event.type === 'session.reset') {
    return []
  }
  if (event.type === 'message.started') {
    return [
      ...messages,
      {
        id: nextMessageId('assistant'),
        role: 'assistant',
        content: '',
        streaming: true,
      },
    ]
  }

  let index = -1
  for (let candidate = messages.length - 1; candidate >= 0; candidate -= 1) {
    const message = messages[candidate]
    if (message.role === 'assistant' && message.streaming) {
      index = candidate
      break
    }
  }
  if (index < 0) {
    return messages
  }
  const next = [...messages]
  const current = next[index]
  next[index] =
    event.type === 'message.delta'
      ? { ...current, content: `${current.content}${event.delta}` }
      : { ...current, streaming: false }
  return next
}

const RECOVERABLE_SEND_ERRORS = new Set([
  'generation_in_progress',
  'message_limit_reached',
  'message_too_large',
])

export function usePlayground({
  namespace,
  slug,
  version,
  enabled = true,
}: UsePlaygroundInput) {
  const runtime = getPlaygroundRuntimeConfig()
  const baseUrl = runtime.enabled ? runtime.baseUrl : undefined
  const [state, setState] = useState<PlaygroundState>(
    enabled && version && baseUrl ? 'connecting' : 'unavailable',
  )
  const [session, setSession] = useState<SidecarSession | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [errorCode, setErrorCode] = useState<string | null>(null)
  const attemptRef = useRef(0)
  const sessionRef = useRef<SidecarSession | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const closeCurrentSession = useCallback(() => {
    eventSourceRef.current?.close()
    eventSourceRef.current = null
    const current = sessionRef.current
    sessionRef.current = null
    if (current && baseUrl) {
      void deleteSidecarSession(baseUrl, current.sessionId).catch(() => {})
    }
  }, [baseUrl])

  const openEventStream = useCallback(
    (sidecarBaseUrl: string, current: SidecarSession) => {
      const source = new EventSource(
        sidecarEventsUrl(sidecarBaseUrl, current.sessionId),
      )
      eventSourceRef.current = source
      source.onopen = () => setState('ready')
      for (const type of [
        'message.started',
        'message.delta',
        'message.completed',
        'session.reset',
      ] as const) {
        source.addEventListener(type, (rawEvent) => {
          const data = JSON.parse((rawEvent as MessageEvent<string>).data) as
            PlaygroundEvent
          setMessages((currentMessages) =>
            applyPlaygroundEvent(currentMessages, data),
          )
          if (data.type === 'message.completed') {
            setIsGenerating(false)
          } else if (data.type === 'session.reset') {
            setIsGenerating(false)
            setErrorCode(null)
          }
        })
      }
      source.addEventListener('session.expired', () => {
        setIsGenerating(false)
        setState('expired')
        source.close()
      })
      source.addEventListener('error', (rawEvent) => {
        const rawData = (rawEvent as MessageEvent<string>).data
        if (typeof rawData === 'string' && rawData) {
          const data = JSON.parse(rawData) as PlaygroundEvent
          if (data.type === 'error') {
            setMessages((currentMessages) =>
              applyPlaygroundEvent(currentMessages, data),
            )
            setIsGenerating(false)
            setErrorCode(data.code)
            setState('ready')
            return
          }
        }
        setIsGenerating(false)
        setState('unavailable')
      })
    },
    [],
  )

  const { mutate: connect } = useMutation({
    mutationFn: async ({
      attempt,
      sidecarBaseUrl,
      selectedVersion,
    }: {
      attempt: number
      sidecarBaseUrl: string
      selectedVersion: string
    }) => {
      const capability = await playgroundCapabilityApi.create(
        namespace,
        slug,
        selectedVersion,
      )
      const nextSession = await createSidecarSession(
        sidecarBaseUrl,
        capability.token,
      )
      return { attempt, sidecarBaseUrl, nextSession }
    },
    onSuccess: ({ attempt, sidecarBaseUrl, nextSession }) => {
      if (attempt !== attemptRef.current) {
        void deleteSidecarSession(
          sidecarBaseUrl,
          nextSession.sessionId,
        ).catch(() => {})
        return
      }
      sessionRef.current = nextSession
      setSession(nextSession)
      openEventStream(sidecarBaseUrl, nextSession)
    },
    onError: (_error, variables) => {
      if (variables.attempt === attemptRef.current) {
        setState('unavailable')
      }
    },
  })

  useEffect(() => {
    attemptRef.current += 1
    const attempt = attemptRef.current
    closeCurrentSession()
    setSession(null)
    setMessages([])
    setIsGenerating(false)
    setErrorCode(null)
    if (!enabled || !version || !baseUrl) {
      setState('unavailable')
      return () => {
        attemptRef.current += 1
      }
    }

    setState('connecting')
    connect({ attempt, sidecarBaseUrl: baseUrl, selectedVersion: version })
    return () => {
      attemptRef.current += 1
      closeCurrentSession()
    }
  }, [baseUrl, closeCurrentSession, connect, enabled, version])

  const { mutate: sendMutation, isPending: isSendPending } = useMutation({
    mutationFn: async (content: string) => {
      const current = sessionRef.current
      if (!baseUrl || !current) {
        throw new SidecarError(404, 'session_not_found')
      }
      await sendSidecarMessage(baseUrl, current.sessionId, content)
    },
    onError: (error) => {
      setIsGenerating(false)
      if (error instanceof SidecarError && error.status === 404) {
        setState('expired')
      } else if (
        error instanceof SidecarError &&
        RECOVERABLE_SEND_ERRORS.has(error.code)
      ) {
        setErrorCode(error.code)
        setState('ready')
      } else {
        setState('unavailable')
      }
    },
  })

  const { mutate: resetMutation } = useMutation({
    mutationFn: async () => {
      const current = sessionRef.current
      if (!baseUrl || !current) {
        throw new SidecarError(404, 'session_not_found')
      }
      await resetSidecarSession(baseUrl, current.sessionId)
    },
    onSuccess: () => {
      setMessages([])
      setIsGenerating(false)
      setErrorCode(null)
    },
    onError: (error) => {
      setState(
        error instanceof SidecarError && error.status === 404
          ? 'expired'
          : 'unavailable',
      )
    },
  })

  const isSending = isGenerating || isSendPending

  const send = useCallback(
    (content: string) => {
      const normalized = content.trim()
      if (!normalized || state !== 'ready' || isSending) {
        return
      }
      setErrorCode(null)
      setIsGenerating(true)
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId('user'),
          role: 'user',
          content: normalized,
        },
      ])
      sendMutation(normalized)
    },
    [isSending, sendMutation, state],
  )

  const reset = useCallback(() => resetMutation(), [resetMutation])

  return {
    state,
    session,
    messages,
    send,
    reset,
    isSending,
    errorCode,
  }
}

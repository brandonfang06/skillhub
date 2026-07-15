import { describe, expect, it } from 'vitest'

import { applyPlaygroundEvent, type ChatMessage } from './use-playground'


describe('applyPlaygroundEvent', () => {
  it('assembles streamed assistant deltas into one message', () => {
    const started = applyPlaygroundEvent([], { type: 'message.started' })
    const firstDelta = applyPlaygroundEvent(started, {
      type: 'message.delta',
      delta: 'Hello',
    })
    const secondDelta = applyPlaygroundEvent(firstDelta, {
      type: 'message.delta',
      delta: ' world',
    })
    const completed = applyPlaygroundEvent(secondDelta, {
      type: 'message.completed',
    })

    expect(completed).toHaveLength(1)
    expect(completed[0]).toMatchObject({
      role: 'assistant',
      content: 'Hello world',
      streaming: false,
      completed: true,
    })
  })

  it('keeps a provider error in the assistant response position', () => {
    const started = applyPlaygroundEvent([], { type: 'message.started' })
    const failed = applyPlaygroundEvent(started, {
      type: 'error',
      code: 'provider_unavailable',
    })

    expect(failed).toHaveLength(1)
    expect(failed[0]).toMatchObject({
      role: 'assistant',
      content: '',
      streaming: false,
      completed: false,
      errorCode: 'provider_unavailable',
    })
  })

  it('preserves partial provider output without marking it completed', () => {
    const started = applyPlaygroundEvent([], { type: 'message.started' })
    const partial = applyPlaygroundEvent(started, {
      type: 'message.delta',
      delta: 'Partial answer',
    })
    const failed = applyPlaygroundEvent(partial, {
      type: 'error',
      code: 'provider_unavailable',
    })

    expect(failed[0]).toMatchObject({
      role: 'assistant',
      content: 'Partial answer',
      streaming: false,
      completed: false,
      errorCode: 'provider_unavailable',
    })
  })

  it('creates an assistant error when the stream fails before start', () => {
    const messages: ChatMessage[] = [
      { id: 'user-1', role: 'user', content: 'Try the model' },
    ]
    const failed = applyPlaygroundEvent(messages, {
      type: 'error',
      code: 'provider_unavailable',
    })

    expect(failed).toHaveLength(2)
    expect(failed[1]).toMatchObject({
      role: 'assistant',
      content: '',
      streaming: false,
      completed: false,
      errorCode: 'provider_unavailable',
    })
  })

  it('maps a compatible incomplete event to a reasoning-only message', () => {
    const started = applyPlaygroundEvent([], { type: 'message.started' })
    const failed = applyPlaygroundEvent(started, {
      type: 'error',
      code: 'response_incomplete',
      reason: 'reasoning_only',
    })

    expect(failed[0]).toMatchObject({
      role: 'assistant',
      errorCode: 'reasoning_only_response',
    })
  })

  it('maps a compatible incomplete event to a visible-output timeout', () => {
    const started = applyPlaygroundEvent([], { type: 'message.started' })
    const failed = applyPlaygroundEvent(started, {
      type: 'error',
      code: 'response_incomplete',
      reason: 'visible_output_timeout',
    })

    expect(failed[0]).toMatchObject({
      role: 'assistant',
      errorCode: 'visible_output_timeout',
    })
  })

  it('clears the local transcript on session reset', () => {
    const messages: ChatMessage[] = [
      { id: 'user-1', role: 'user', content: 'hello' },
    ]

    expect(
      applyPlaygroundEvent(messages, { type: 'session.reset' }),
    ).toEqual([])
  })
})

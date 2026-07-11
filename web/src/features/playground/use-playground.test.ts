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

  it('removes an empty assistant placeholder after a provider error', () => {
    const started = applyPlaygroundEvent([], { type: 'message.started' })
    const failed = applyPlaygroundEvent(started, {
      type: 'error',
      code: 'provider_unavailable',
    })

    expect(failed).toEqual([])
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

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

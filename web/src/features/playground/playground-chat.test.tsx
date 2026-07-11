import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { PlaygroundChat } from './playground-chat'


vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('PlaygroundChat', () => {
  it('locks prompt input while a model response is streaming', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="ready"
        messages={[
          {
            id: 'assistant-1',
            role: 'assistant',
            content: 'Working',
            streaming: true,
          },
        ]}
        isSending
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toMatch(/<textarea[^>]*disabled=""/)
  })
})

// @vitest-environment jsdom

import { renderToStaticMarkup } from 'react-dom/server'
import { render } from '@testing-library/react'
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
        namespace="global"
        slug="notes"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toMatch(/<textarea[^>]*disabled=""/)
  })

  it('offers the existing install command after a completed response', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="ready"
        messages={[
          {
            id: 'assistant-1',
            role: 'assistant',
            content: 'Complete',
            streaming: false,
            completed: true,
          },
        ]}
        isSending={false}
        namespace="global"
        slug="notes"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toContain('data-playground-install-cta="true"')
    expect(html).toContain('playground.installReady')
    expect(html).toContain('npx @astron-team/skillhub@latest install notes')
  })

  it('does not offer installation while the response is streaming', () => {
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
        namespace="global"
        slug="notes"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).not.toContain('data-playground-install-cta')
  })

  it('does not offer installation after a provider error', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="ready"
        messages={[
          {
            id: 'assistant-1',
            role: 'assistant',
            content: '',
            streaming: false,
            completed: false,
          },
        ]}
        isSending={false}
        namespace="global"
        slug="notes"
        errorCode="provider_unavailable"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).not.toContain('data-playground-install-cta')
    expect(html).toContain('playground.errors.provider_unavailable')
  })

  it('renders a generation failure in the assistant response position', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="ready"
        messages={[
          {
            id: 'assistant-1',
            role: 'assistant',
            content: '',
            streaming: false,
            completed: false,
            errorCode: 'reasoning_only_response',
          },
        ]}
        isSending={false}
        namespace="global"
        slug="notes"
        errorCode="reasoning_only_response"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toContain('data-playground-message-error="true"')
    expect(html).toContain('playground.errors.reasoning_only_response')
    expect(
      html.match(/playground\.errors\.reasoning_only_response/g),
    ).toHaveLength(1)
  })

  it('keeps truncated output without offering installation', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="ready"
        messages={[
          {
            id: 'assistant-1',
            role: 'assistant',
            content: 'Partial answer',
            streaming: false,
            completed: false,
          },
        ]}
        isSending={false}
        namespace="global"
        slug="notes"
        errorCode="output_truncated"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toContain('Partial answer')
    expect(html).toContain('playground.errors.output_truncated')
    expect(html).not.toContain('data-playground-install-cta')
  })

  it('hides an earlier install CTA when the latest response is truncated', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="ready"
        messages={[
          {
            id: 'assistant-1',
            role: 'assistant',
            content: 'Complete answer',
            completed: true,
          },
          {
            id: 'assistant-2',
            role: 'assistant',
            content: 'Partial answer',
            completed: false,
          },
        ]}
        isSending={false}
        namespace="global"
        slug="notes"
        errorCode="output_truncated"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).not.toContain('data-playground-install-cta')
  })

  it('renders a reload action for an expired session', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="expired"
        messages={[
          {
            id: 'user-1',
            role: 'user',
            content: 'Previous prompt must be hidden',
          },
        ]}
        isSending={false}
        namespace="global"
        slug="notes"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toContain('playground.reload')
    expect(html).not.toContain('Previous prompt must be hidden')
    expect(html).toMatch(/<textarea[^>]*disabled=""/)
  })

  it('renders a retry action when the playground is temporarily unavailable', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="unavailable"
        messages={[]}
        isSending={false}
        namespace="global"
        slug="notes"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toContain('playground.reload')
  })

  it('keeps a failed response visible when the event stream disconnects', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="unavailable"
        messages={[
          { id: 'user-1', role: 'user', content: 'Try the model' },
          {
            id: 'assistant-1',
            role: 'assistant',
            content: '',
            completed: false,
            errorCode: 'provider_unavailable',
          },
        ]}
        isSending={false}
        namespace="global"
        slug="notes"
        errorCode="provider_unavailable"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toContain('Try the model')
    expect(html).toContain('data-playground-message-error="true"')
    expect(html).toContain('playground.reload')
  })

  it('keeps the latest message visible as the transcript grows', () => {
    const scrollIntoView = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })
    const props = {
      state: 'ready' as const,
      isSending: false,
      namespace: 'global',
      slug: 'notes',
      onSend: vi.fn(),
      onReset: vi.fn(),
    }
    const { rerender } = render(
      <PlaygroundChat {...props} messages={[]} />,
    )

    scrollIntoView.mockClear()
    rerender(
      <PlaygroundChat
        {...props}
        messages={[{ id: 'user-1', role: 'user', content: 'Latest prompt' }]}
      />,
    )

    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'end' })
  })

  it('keeps mobile chat actions at least 44 pixels tall', () => {
    const html = renderToStaticMarkup(
      <PlaygroundChat
        state="ready"
        messages={[
          {
            id: 'assistant-1',
            role: 'assistant',
            content: 'Complete',
            completed: true,
          },
        ]}
        isSending={false}
        namespace="global"
        slug="notes"
        onSend={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(html).toMatch(/class="[^"]*h-11[^"]*"[^>]*aria-label="playground.reset"/)
    expect(html).toMatch(/class="[^"]*h-11[^"]*"[^>]*aria-label="playground.copyInstallCommand"/)
    expect(html).toMatch(/class="[^"]*h-11[^"]*"[^>]*aria-label="playground.send"/)
  })
})

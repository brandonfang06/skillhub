import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/i18n/config'

const errorSpy = vi.fn()

vi.mock('./toast', () => ({
  toast: {
    error: errorSpy,
  },
}))

describe('ApiError', () => {
  beforeEach(async () => {
    errorSpy.mockReset()
    await i18n.changeLanguage('zh')
  })

  it('keeps the provided server message key', async () => {
    const { ApiError } = await import('./api-error')

    const error = new ApiError(
      'apiError.unknown',
      400,
      'server message',
      'error.server.key',
      'request-123',
      ['arg-1'],
    )

    expect(error.serverMessageKey).toBe('error.server.key')
    expect(error.requestId).toBe('request-123')
    expect(error.serverMessageArgs).toEqual(['arg-1'])
  })
})

describe('handleApiError', () => {
  beforeEach(async () => {
    errorSpy.mockReset()
    await i18n.changeLanguage('zh')
    vi.stubGlobal('window', { location: { href: '' } })
  })

  it('redirects to login for unauthorized api errors', async () => {
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError('apiError.unauthorized', 401))

    expect(errorSpy).toHaveBeenCalled()
    expect(window.location.href).toBe('/login')
  })

  it('preserves disabled-account reason when redirecting to login', async () => {
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError('This account has been disabled', 401, 'This account has been disabled'))

    expect(errorSpy).not.toHaveBeenCalled()
    expect(window.location.href).toBe('/login?reason=accountDisabled')
  })

  it('recognizes a Russian disabled-account response while another locale is active', async () => {
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError(
      'Эта учётная запись отключена',
      401,
      'Эта учётная запись отключена',
    ))

    expect(errorSpy).not.toHaveBeenCalled()
    expect(window.location.href).toBe('/login?reason=accountDisabled')
  })

  it('keeps unauthorized redirects inside the runtime application base', async () => {
    vi.stubGlobal('window', {
      __SKILLHUB_RUNTIME_CONFIG__: { basePath: '/skillhub' },
      location: { href: '' },
    })
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError('apiError.unauthorized', 401))

    expect(window.location.href).toBe('/skillhub/login')
  })

  it('falls back to the server message for non-standard api errors', async () => {
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError('apiError.unknown', 422, 'Server said no'))

    expect(errorSpy).toHaveBeenLastCalledWith('Server said no')
  })

  it('shows a localized API-token scope denial with its request ID', async () => {
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError(
      'error.apiToken.scope.missing',
      403,
      'error.apiToken.scope.missing',
      'error.apiToken.scope.missing',
      'scope-request',
      ['skill:publish'],
    ))

    expect(errorSpy).toHaveBeenLastCalledWith(
      expect.stringContaining('skill:publish'),
      expect.stringContaining('scope-request'),
    )
  })

  it('does not expose unknown server text for forbidden responses', async () => {
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError(
      'database policy details',
      403,
      'database policy details',
      'database policy details',
      'forbidden-request',
    ))

    expect(errorSpy).toHaveBeenLastCalledWith(
      i18n.t('apiError.forbidden'),
      expect.stringContaining('forbidden-request'),
    )
  })

  it('shows network error message when status is 0 (network disconnected)', async () => {
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError('Network error', 0))

    expect(errorSpy).toHaveBeenLastCalledWith('网络连接失败，请检查网络')
  })

  it('shows network error message when status is 0 with timeout', async () => {
    const { ApiError, handleApiError } = await import('./api-error')

    handleApiError(new ApiError('error.request.timeout', 0))

    expect(errorSpy).toHaveBeenLastCalledWith('网络连接失败，请检查网络')
  })
})

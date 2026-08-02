/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'
import nginxConfig from '../../nginx.conf.template?raw'

describe('forwarded protocol policy', () => {
  it('ignores client-supplied protocol unless a trusted proxy is enabled', () => {
    expect(nginxConfig).toContain('set $proxy_x_forwarded_proto $scheme;')
    expect(nginxConfig).toContain(
      'set $forwarded_proto_source "${SKILLHUB_TRUST_FORWARDED_PROTO}:$http_x_forwarded_proto";',
    )
    expect(nginxConfig).toContain('if ($forwarded_proto_source ~* "^true:https$")')
    expect(nginxConfig).toContain('if ($forwarded_proto_source ~* "^true:http$")')
  })

  it.each(['/api/', '/oauth2/', '/login/oauth2/', '/.well-known/'])(
    'uses the sanitized protocol for %s',
    (location) => {
      const escapedLocation = location.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      expect(nginxConfig).toMatch(
        new RegExp(
          `location ${escapedLocation} \\{[\\s\\S]*?proxy_set_header X-Forwarded-Proto \\$proxy_x_forwarded_proto;[\\s\\S]*?\\}`,
        ),
      )
    },
  )
})

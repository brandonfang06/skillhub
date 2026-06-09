import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import http from 'node:http'
import https from 'node:https'
import path from 'path'

const LEGACY_BROWSER_TARGETS = ['chrome83', 'edge83', 'firefox78', 'safari14']

export type MethodAwareProxyRule = {
  methods: string[]
  pattern: RegExp
  target: string
}

export const METHOD_AWARE_PROXY_RULES: MethodAwareProxyRule[] = [
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/skills(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/skills\/[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/skills\/[^/?]+\/(?!undelete(?:\?.*)?$)[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/skills\/[^/?]+\/[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/reviews\/[^/?]+\/approve(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/reviews\/[^/?]+\/approve(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/reviews\/[^/?]+\/reject(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/reviews\/[^/?]+\/reject(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/reviews\/[^/?]+\/withdraw(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/reviews\/[^/?]+\/withdraw(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/reviews(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/reviews(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/reviews(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/reviews(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/reviews\/(?:pending|my-submissions)(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/reviews\/(?:pending|my-submissions)(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/reviews\/[^/?]+\/skill-detail(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/reviews\/[^/?]+\/skill-detail(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/reviews\/[^/?]+\/file(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/reviews\/[^/?]+\/file(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/reviews\/[^/?]+\/download(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/reviews\/[^/?]+\/download(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/reviews\/(?!pending(?:\?.*)?$|my-submissions(?:\?.*)?$)[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/reviews\/(?!pending(?:\?.*)?$|my-submissions(?:\?.*)?$)[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/promotions(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/promotions(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/promotions\/pending(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/promotions\/pending(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/promotions\/(?!pending(?:\?.*)?$)[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/promotions\/(?!pending(?:\?.*)?$)[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/promotions(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/promotions(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/promotions\/[^/?]+\/reject(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/promotions\/[^/?]+\/reject(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/promotions\/[^/?]+\/approve(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/promotions\/[^/?]+\/approve(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/admin\/skills\/\d+\/hide(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/admin\/skills\/\d+\/unhide(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/admin\/skills\/versions\/\d+\/yank(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET', 'PUT'],
    pattern: /^\/api\/v1\/skills\/\d+\/star(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET', 'PUT'],
    pattern: /^\/api\/web\/skills\/\d+\/star(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET', 'PUT'],
    pattern: /^\/api\/v1\/skills\/\d+\/subscription(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET', 'PUT'],
    pattern: /^\/api\/web\/skills\/\d+\/subscription(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET', 'PUT'],
    pattern: /^\/api\/v1\/skills\/\d+\/rating(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET', 'PUT'],
    pattern: /^\/api\/web\/skills\/\d+\/rating(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/me\/stars(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/me\/stars(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/v1\/me\/subscriptions(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['GET'],
    pattern: /^\/api\/web\/me\/subscriptions(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/skills\/[^/?]+\/[^/?]+\/archive(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/skills\/[^/?]+\/[^/?]+\/archive(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/skills\/[^/?]+\/[^/?]+\/unarchive(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/skills\/[^/?]+\/[^/?]+\/unarchive(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['DELETE'],
    pattern: /^\/api\/v1\/skills\/[^/?]+\/[^/?]+\/versions\/[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['DELETE'],
    pattern: /^\/api\/web\/skills\/[^/?]+\/[^/?]+\/versions\/[^/?]+(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/skills\/[^/?]+\/[^/?]+\/versions\/[^/?]+\/withdraw-review(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/skills\/[^/?]+\/[^/?]+\/versions\/[^/?]+\/withdraw-review(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/skills\/[^/?]+\/[^/?]+\/versions\/[^/?]+\/rerelease(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/skills\/[^/?]+\/[^/?]+\/versions\/[^/?]+\/rerelease(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/skills\/[^/?]+\/[^/?]+\/submit-review(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/skills\/[^/?]+\/[^/?]+\/submit-review(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/v1\/skills\/[^/?]+\/[^/?]+\/confirm-publish(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
  {
    methods: ['POST'],
    pattern: /^\/api\/web\/skills\/[^/?]+\/[^/?]+\/confirm-publish(?:\?.*)?$/,
    target: 'http://localhost:8081',
  },
]

export function resolveMethodAwareProxyTarget(
  method: string | undefined,
  pathname: string | undefined,
  rules: MethodAwareProxyRule[] = METHOD_AWARE_PROXY_RULES,
): string | undefined {
  if (!method || !pathname) {
    return undefined
  }

  const normalizedMethod = method.toUpperCase()
  return rules.find((rule) => rule.methods.includes(normalizedMethod) && rule.pattern.test(pathname))?.target
}

function methodAwareProxyPlugin(rules: MethodAwareProxyRule[] = METHOD_AWARE_PROXY_RULES): Plugin {
  return {
    name: 'skillhub-method-aware-proxy',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const target = resolveMethodAwareProxyTarget(req.method, req.url, rules)
        if (!target || !req.url) {
          next()
          return
        }

        const targetUrl = new URL(req.url, target)
        const transport = targetUrl.protocol === 'https:' ? https : http
        const proxyRequest = transport.request(
          targetUrl,
          {
            method: req.method,
            headers: {
              ...req.headers,
              host: targetUrl.host,
            },
          },
          (proxyResponse) => {
            res.writeHead(proxyResponse.statusCode ?? 502, proxyResponse.headers)
            proxyResponse.pipe(res)
          },
        )

        proxyRequest.on('error', () => {
          if (!res.headersSent) {
            res.writeHead(502)
          }
          res.end()
        })

        req.pipe(proxyRequest)
      })
    },
  }
}

export default defineConfig({
  plugins: [methodAwareProxyPlugin(), react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    target: LEGACY_BROWSER_TARGETS,
    cssTarget: LEGACY_BROWSER_TARGETS,
  },
  optimizeDeps: {
    esbuildOptions: {
      target: LEGACY_BROWSER_TARGETS,
    },
  },
  test: {
    exclude: ['**/node_modules/**', '**/e2e/**'],
  },
  server: {
    port: 3000,
    watch: {
      usePolling: true,
      interval: 150,
    },
    proxy: {
      '/.well-known/clawhub.json': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '/api/v1/health': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/search(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/resolve(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/resolve/[^/]+(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/download(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/download/[^/]+(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/auth/me(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '/api/v1/labels': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '/api/web/labels': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/publish(?:\\?.*)?$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/labels$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/labels$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/resolve$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/resolve$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/versions$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/versions$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/versions/compare$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/versions/compare$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/file$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/file$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/download$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/download$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/download$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/cli/v1/skills/[^/]+/publish/validate$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/cli/v1/skills/[^/]+/publish$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/publish$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/publish$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/versions/(?!compare$)[^/]+$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/versions/(?!compare$)[^/]+$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/tags/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/oauth2': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})

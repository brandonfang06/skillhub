import { readFileSync } from 'node:fs'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const LEGACY_BROWSER_TARGETS = ['chrome83', 'edge83', 'firefox78', 'safari14']
const JS_BUILD_TARGET = 'es2020'
const PYTHON_BACKEND_TARGET = 'http://localhost:8080'
const guideTemplate = readFileSync(path.resolve(__dirname, 'src/docs/skill.md.template'), 'utf8')
const safeHostPattern = /^(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(?::[0-9]{1,5})?$/

function installGuideDevPlugin(): Plugin {
  const configuredBase = (process.env.VITE_BASE_PATH ?? '').replace(/^\/+|\/+$/g, '')
  const basePrefix = configuredBase ? `/${configuredBase}` : ''
  const guidePaths = new Set([
    '/install/skillhub.md',
    '/registry/skill.md',
    `${basePrefix}/install/skillhub.md`,
    `${basePrefix}/registry/skill.md`,
  ])

  return {
    name: 'skillhub-install-guide-dev',
    configureServer(server) {
      return () => {
        server.middlewares.use((request, response, next) => {
          const requestPath = new URL(request.originalUrl ?? request.url ?? '/', 'http://localhost').pathname
          if (!guidePaths.has(requestPath)) {
            next()
            return
          }
          const host = request.headers.host
          if (!host || !safeHostPattern.test(host)) {
            response.statusCode = 400
            response.end('Invalid Host')
            return
          }
          const publicBaseUrl = `http://${host}${basePrefix}`
          const guide = guideTemplate
            .replaceAll('${SKILLHUB_PUBLIC_BASE_URL}', publicBaseUrl)
            .replaceAll('${SKILLHUB_WEB_CLI_REGISTRY_URL}', publicBaseUrl)
          response.statusCode = 200
          response.setHeader('Content-Type', 'text/markdown; charset=utf-8')
          response.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate')
          response.end(guide)
        })
      }
    },
  }
}

export const PYTHON_BACKEND_PROXY_PREFIXES = [
  '/api',
  '/oauth2',
  '/login/oauth2',
  '/.well-known',
] as const

function pythonBackendProxy() {
  return Object.fromEntries(
    PYTHON_BACKEND_PROXY_PREFIXES.map((prefix) => [
      prefix,
      {
        target: PYTHON_BACKEND_TARGET,
        changeOrigin: true,
      },
    ]),
  )
}

export default defineConfig({
  base: './',
  plugins: [installGuideDevPlugin(), react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    target: JS_BUILD_TARGET,
    cssTarget: LEGACY_BROWSER_TARGETS,
  },
  optimizeDeps: {
    esbuildOptions: {
      target: JS_BUILD_TARGET,
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
    proxy: pythonBackendProxy(),
  },
})

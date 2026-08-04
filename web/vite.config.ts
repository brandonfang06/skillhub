import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const LEGACY_BROWSER_TARGETS = ['chrome83', 'edge83', 'firefox78', 'safari14']
const JS_BUILD_TARGET = 'es2020'
const PYTHON_BACKEND_TARGET = 'http://localhost:8080'

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
  plugins: [react()],
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

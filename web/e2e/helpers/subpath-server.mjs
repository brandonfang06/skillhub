import { createReadStream } from 'node:fs'
import { readFile, stat } from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const publicPort = Number(process.env.SKILLHUB_E2E_PUBLIC_PORT ?? 3190)
const upstreamPort = Number(process.env.SKILLHUB_E2E_UPSTREAM_PORT ?? 3191)
const basePath = '/skillhub'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../dist')
const indexTemplate = await readFile(path.join(root, 'index.html'), 'utf8')
const indexHtml = indexTemplate.replace('<base href="/" />', `<base href="${basePath}/" />`)

const contentTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.md', 'text/markdown; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.woff2', 'font/woff2'],
])

function send(response, status, contentType, body, headers = {}) {
  response.writeHead(status, { 'Content-Type': contentType, ...headers })
  response.end(body)
}

function runtimeConfig() {
  return `window.__SKILLHUB_RUNTIME_CONFIG__ = ${JSON.stringify({
    apiBaseUrl: '',
    appBaseUrl: `http://127.0.0.1:${publicPort}${basePath}`,
    basePath,
    cliRegistryUrl: '',
    authDirectEnabled: 'false',
    authDirectProvider: '',
    localRegistrationEnabled: 'false',
    authSessionBootstrapEnabled: 'false',
    authSessionBootstrapProvider: '',
    authSessionBootstrapAuto: 'false',
    playgroundEnabled: 'false',
    playgroundBaseUrl: '',
  })};\n`
}

async function serveUpstream(request, response) {
  const url = new URL(request.url ?? '/', `http://127.0.0.1:${upstreamPort}`)
  let pathname
  try {
    pathname = decodeURIComponent(url.pathname)
  } catch {
    send(response, 400, 'text/plain; charset=utf-8', 'bad path')
    return
  }

  if (pathname === '/nginx-health') {
    send(response, 200, 'text/plain; charset=utf-8', 'ok')
    return
  }
  if (pathname === '/runtime-config.js') {
    send(response, 200, 'text/javascript; charset=utf-8', runtimeConfig(), { 'Cache-Control': 'no-store' })
    return
  }

  const relativePath = pathname.replace(/^\/+/, '')
  const filePath = path.resolve(root, relativePath)
  if (filePath !== root && !filePath.startsWith(`${root}${path.sep}`)) {
    send(response, 400, 'text/plain; charset=utf-8', 'bad path')
    return
  }

  try {
    const metadata = await stat(filePath)
    if (metadata.isFile()) {
      response.writeHead(200, {
        'Content-Type': contentTypes.get(path.extname(filePath)) ?? 'application/octet-stream',
        'Cache-Control': pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache',
      })
      createReadStream(filePath).pipe(response)
      return
    }
  } catch {
    // Extensionless routes fall through to the SPA document.
  }

  if (!path.extname(pathname)) {
    send(response, 200, 'text/html; charset=utf-8', indexHtml, { 'Cache-Control': 'no-cache' })
    return
  }
  send(response, 404, 'text/plain; charset=utf-8', 'not found')
}

export async function startSubpathServer() {
  const upstream = http.createServer((request, response) => {
    void serveUpstream(request, response).catch((error) => {
      send(response, 500, 'text/plain; charset=utf-8', String(error))
    })
  })

  const proxy = http.createServer((request, response) => {
    const url = new URL(request.url ?? '/', `http://127.0.0.1:${publicPort}`)
    if (url.pathname !== basePath && !url.pathname.startsWith(`${basePath}/`)) {
      send(response, 404, 'text/plain; charset=utf-8', 'not found')
      return
    }

    const rewrittenPath = `${url.pathname.slice(basePath.length) || '/'}${url.search}`
    const upstreamRequest = http.request(
      {
        hostname: '127.0.0.1',
        port: upstreamPort,
        method: request.method,
        path: rewrittenPath,
        headers: { ...request.headers, host: `127.0.0.1:${upstreamPort}` },
      },
      (upstreamResponse) => {
        response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers)
        upstreamResponse.pipe(response)
      },
    )
    upstreamRequest.on('error', (error) => {
      send(response, 502, 'text/plain; charset=utf-8', String(error))
    })
    request.pipe(upstreamRequest)
  })

  await new Promise((resolve) => upstream.listen(upstreamPort, '127.0.0.1', resolve))
  await new Promise((resolve) => proxy.listen(publicPort, '127.0.0.1', resolve))
  process.stdout.write(`SkillHub subpath E2E proxy listening on http://127.0.0.1:${publicPort}${basePath}\n`)

  return async () => {
    await Promise.all([
      new Promise((resolve) => {
        proxy.close(resolve)
        proxy.closeAllConnections()
      }),
      new Promise((resolve) => {
        upstream.close(resolve)
        upstream.closeAllConnections()
      }),
    ])
  }
}

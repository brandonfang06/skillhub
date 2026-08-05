import { execFile } from 'node:child_process'
import path from 'node:path'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'

const execFileAsync = promisify(execFile)
const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')

async function buildSubpathBundle() {
  await execFileAsync(process.execPath, [
    path.resolve(webRoot, 'node_modules/typescript/bin/tsc'),
    '-b',
  ], { cwd: webRoot })
  await execFileAsync(process.execPath, [
    path.resolve(webRoot, 'node_modules/vite/bin/vite.js'),
    'build',
  ], { cwd: webRoot })
}

export default async function globalSetup() {
  await buildSubpathBundle()
  const { startSubpathServer } = await import('./subpath-server.mjs')
  return startSubpathServer()
}

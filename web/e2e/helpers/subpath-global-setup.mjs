import { startSubpathServer } from './subpath-server.mjs'

export default async function globalSetup() {
  return startSubpathServer()
}

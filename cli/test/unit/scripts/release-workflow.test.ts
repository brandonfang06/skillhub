import { describe, expect, test } from 'bun:test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const workflowRoot = resolve(
  import.meta.dir,
  '../../../../.github/workflows'
)

async function workflow(name: string): Promise<string> {
  return readFile(resolve(workflowRoot, name), 'utf-8')
}

describe('CLI workflows', () => {
  test('keeps the three-OS PR matrix and validates release workflow changes', async () => {
    const source = await workflow('pr-cli.yml')

    expect(source).toContain('os: [ubuntu-latest, macos-latest, windows-latest]')
    expect(source).toContain("'.github/workflows/release-cli.yml'")
    for (const command of [
      'bun run lint',
      'bun run typecheck',
      'bun test',
      'bun run build',
      'node dist/index.js version'
    ]) {
      expect(source).toContain(command)
    }
  })

  test('isolates internal Nexus publication on the approved runner without public fallbacks', async () => {
    const source = await workflow('release-cli.yml')
    const publishJob = source
      .split('\n  publish-npm:')[1]!
      .split('\n  create-release:')[0]!

    expect(source).toMatch(/build-and-test:[\s\S]*runs-on: ubuntu-latest/)
    expect(publishJob).toContain(
      'runs-on: [self-hosted, linux, skillhub-nexus]'
    )
    expect(publishJob).toContain(
      'NPM_PUBLISH_REGISTRY: ${{ vars.NPM_PUBLISH_REGISTRY }}'
    )
    expect(publishJob).toContain(
      'NPM_INSTALL_REGISTRY: ${{ vars.NPM_INSTALL_REGISTRY }}'
    )
    expect(publishJob).toContain(
      'NPM_CONFIG_USERCONFIG: ${{ runner.temp }}/skillhub-cli-release.npmrc'
    )
    expect(publishJob).toContain(
      'EXPECTED_SHA256: ${{ needs.build-and-test.outputs.package_sha256 }}'
    )
    expect(source).toContain('vars.NPM_PACKAGE_NAME')
    expect(source).toContain('secrets.NPM_TOKEN')
    expect(publishJob).not.toContain('registry.npmjs.org')
    expect(publishJob).not.toContain('vars.NPM_REGISTRY')
    expect(publishJob).not.toContain('~/.npmrc')
    expect(publishJob).toContain('[ -z "$NPM_PUBLISH_REGISTRY" ]')
    expect(publishJob).toContain('[ -z "$NPM_INSTALL_REGISTRY" ]')
    expect(source).toContain('npm publish')
    expect(publishJob).toMatch(
      /npm publish[\s\S]*--registry "\$NPM_PUBLISH_REGISTRY"/
    )
  })

  test('cleans ephemeral npm credentials even when publication fails', async () => {
    const source = await workflow('release-cli.yml')
    const publishJob = source
      .split('\n  publish-npm:')[1]!
      .split('\n  create-release:')[0]!

    expect(publishJob).toContain(
      'printf \'//%s/:_authToken=%s\\n\' "$REGISTRY_KEY" "$NPM_TOKEN" >> "$NPM_CONFIG_USERCONFIG"'
    )
    expect(publishJob).toContain(
      "printf 'always-auth=true\\n' >> \"$NPM_CONFIG_USERCONFIG\""
    )
    expect(publishJob).toMatch(
      /- name: Remove npm credentials\s+if: always\(\)\s+run: rm -f "\$NPM_CONFIG_USERCONFIG"/
    )
  })

  test('downloads hosted and install artifacts and compares both digests', async () => {
    const source = await workflow('release-cli.yml')
    const publishJob = source
      .split('\n  publish-npm:')[1]!
      .split('\n  create-release:')[0]!

    expect(publishJob).toContain(
      'for VERIFY_NAME in hosted install; do'
    )
    expect(publishJob).toContain(
      'VERIFY_REGISTRY="$NPM_PUBLISH_REGISTRY"'
    )
    expect(publishJob).toContain(
      'VERIFY_REGISTRY="$NPM_INSTALL_REGISTRY"'
    )
    expect(publishJob).toContain(
      'npm pack "${PACKAGE_NAME}@${VERSION}"'
    )
    expect(publishJob).toContain(
      'VERIFY_ROOT=$(mktemp -d "$RUNNER_TEMP/skillhub-cli-registry-verify.XXXXXX")'
    )
    expect(publishJob).toContain(
      '--pack-destination "$VERIFY_ROOT/$VERIFY_NAME"'
    )
    expect(publishJob).toContain(
      'REMOTE_SHA256=$(sha256sum'
    )
    expect(publishJob).toContain(
      'if [ "$REMOTE_SHA256" != "$EXPECTED_SHA256" ]; then'
    )
    expect(publishJob).toContain(
      'Registry artifact digest mismatch'
    )
  })

  test('packs one immutable tarball with source and SHA-256 evidence', async () => {
    const source = await workflow('release-cli.yml')

    expect(source).toContain('npm pack --json')
    expect(source).toContain('sha256sum')
    expect(source).toContain('cli-release-metadata.json')
    expect(source).toContain('sourceCommit')
    expect(source).toContain('packageSha256')
    expect(source).toContain('github.sha')
  })

  test('supports a package-only dry run without publish or GitHub release', async () => {
    const source = await workflow('release-cli.yml')

    expect(source).toMatch(/dry_run:[\s\S]*type: boolean/)
    expect(source).toMatch(/publish-npm:[\s\S]*if:[^\n]*!inputs\.dry_run/)
    expect(source).toMatch(/create-release:[\s\S]*if:[^\n]*!inputs\.dry_run/)
  })
})

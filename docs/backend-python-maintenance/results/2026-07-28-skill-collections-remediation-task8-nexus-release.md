# Skill Collections Remediation Task 8: Nexus CLI Release

Date: 2026-07-28

## Outcome

The CLI release workflow now keeps build/test on `ubuntu-latest` and confines
Nexus publication to a self-hosted Linux runner carrying the
`skillhub-nexus` label. Publication requires explicit hosted and install/group
registry variables and has no npmjs or legacy single-registry fallback.

The publish job writes authentication only to
`${{ runner.temp }}/skillhub-cli-release.npmrc`, removes that file with an
`if: always()` step, and compares tarballs downloaded separately from the
hosted and install/group registries with the SHA-256 produced by the build job.
An already-published version with different bytes therefore fails closed.

## TDD Evidence

Before the workflow implementation:

```text
bun test test\unit\scripts\release-workflow.test.ts
3 pass, 3 fail
```

The failures covered the missing internal runner boundary, temporary credential
file/cleanup, and hosted/group byte verification.

After implementation:

```text
bun test test\unit\scripts\release-workflow.test.ts
6 pass, 0 fail, 43 expect() calls
```

## No-Publish Rehearsal

```text
bun run build
Bundled 179 modules; dist/index.js generated successfully.

npm.cmd pack --dry-run --json --cache .tmp-npm-cache
exit 0; @astron-team/skillhub@0.1.9; four package entries.
```

The first `npm pack` invocation through PowerShell's `npm.ps1` was blocked by
the local execution policy. A second attempt using the default user npm cache
was blocked by sandbox write permissions. The successful command used
`npm.cmd` and an isolated cache inside the CLI workspace; that temporary cache
was removed after the check.

No Nexus request, package publication, GitHub Release, commit, push, or
deployment was performed.

## Operator Contract

- Required runner labels: `self-hosted`, `linux`, `skillhub-nexus`.
- Required variables: `NPM_PUBLISH_REGISTRY`, `NPM_INSTALL_REGISTRY`.
- Optional package override: `NPM_PACKAGE_NAME`.
- Required secret: `NPM_TOKEN`.
- Hosted and group tarball SHA-256 values must both equal the immutable build
  artifact digest.
- Real Nexus connectivity, permissions, caching, and publication remain an
  external authorization and rollout gate.

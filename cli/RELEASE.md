# CLI Release Guide

## Overview

CLI releases use a PR-based flow. `make publish-cli` prepares a release branch
and PR. After that PR is merged, a `cli-vX.Y.Z` tag triggers
[`release-cli.yml`](../.github/workflows/release-cli.yml).

The workflow builds and tests once, creates one immutable npm tarball, records
its source commit and SHA-256, and passes that same artifact to publication and
GitHub Release jobs. It never rebuilds the package in the publish job.

Publication is internal-only. The build job stays on a GitHub-hosted runner,
while the publish job runs on an approved self-hosted runner that can reach the
organization's Nexus hosted and group repositories.

## Repository Configuration

Configure these under GitHub repository **Settings → Secrets and variables →
Actions**.

### Secret

- `NPM_TOKEN` — npm automation token with permission to publish to the hosted
  registry and read from the install/group registry. It is never stored in an
  artifact or printed by the workflow.

### Variables

- `NPM_PUBLISH_REGISTRY` — required hosted registry used by `npm publish`.
- `NPM_INSTALL_REGISTRY` — required group registry used by employees and by
  post-publish verification.
- `NPM_PACKAGE_NAME` — optional internal package coordinate, for example
  `@company/skillhub`.

The publish workflow has no `NPM_REGISTRY` or public npm fallback. A missing
hosted or group URL fails before publication. Package-name resolution remains:

| Purpose | Resolution order |
| --- | --- |
| Publish | required `NPM_PUBLISH_REGISTRY` |
| Install/verify | required `NPM_INSTALL_REGISTRY` |
| Package name | `NPM_PACKAGE_NAME` → `name` in `cli/package.json` |

Do not commit an internal Nexus URL, package coordinate, or token. The URL and
package name are repository variables; the token is a repository or
environment secret.

The `publish-npm` job requires a self-hosted runner with all three labels:
`self-hosted`, `linux`, and `skillhub-nexus`. The runner must resolve Nexus,
trust its TLS chain, and have `npm`, Node.js, and `sha256sum`. Keep the build
job on `ubuntu-latest`; it does not need Nexus connectivity or credentials.

### Nexus Example

The actual organization URLs belong in GitHub variables:

```text
NPM_PUBLISH_REGISTRY=https://nexus.example.com/repository/npm-hosted/
NPM_INSTALL_REGISTRY=https://nexus.example.com/repository/npm-group/
NPM_PACKAGE_NAME=@company/skillhub
```

Employees can then install through the group repository:

```bash
npm install -g @company/skillhub@<version> \
  --registry https://nexus.example.com/repository/npm-group/
```

The CLI's own `--registry` flag is different: it selects the SkillHub HTTP API,
not the npm/Nexus package repository.

## Release Process

### 1. Prepare the release PR

From a clean `main` branch:

```bash
make publish-cli
make publish-cli-minor
make publish-cli-major
```

[`scripts/publish-cli.sh`](../scripts/publish-cli.sh) runs local gates, computes
the next `cli-v*` version, creates a release branch, pushes it, and opens a PR.

### 2. Merge and tag

After the PR is merged:

```bash
git fetch origin main
git tag cli-vX.Y.Z origin/main
git push origin cli-vX.Y.Z
```

### 3. CI packages and publishes

The workflow has three jobs:

1. `build-and-test`
   - validates the tag;
   - applies the configured package name and tag version;
   - runs lint, typecheck, tests, build, and runtime-version verification;
   - runs `npm pack --json` once;
   - uploads the tarball, SHA-256, release files, and
     `cli-release-metadata.json`.
2. `publish-npm`
   - downloads the immutable artifact without checking out or rebuilding;
   - checks the exact package/version in the hosted registry;
   - publishes the tarball only when absent;
   - downloads the exact version from both hosted and install/group
     registries;
   - compares both downloaded SHA-256 values with the build artifact digest;
   - fails if an existing version contains different bytes;
   - writes npm credentials only to
     `${{ runner.temp }}/skillhub-cli-release.npmrc` and removes the file with
     an `if: always()` cleanup step.
3. `create-release`
   - creates source-independent CLI archives from the uploaded files;
   - attaches the npm tarball, metadata, and checksums to the GitHub Release.

The metadata records `package`, `version`, `sourceCommit`, workflow commit,
tarball name, and `packageSha256`. Job summaries repeat the package identity,
source commit, and digest for operator review.

## Package-Only Dry Run

Use **Actions → Release CLI → Run workflow**, enter an existing
`cli-vX.Y.Z` tag, and enable `dry_run`.

A dry run performs all build, test, runtime-version, pack, checksum, and
artifact-upload steps. It skips both registry publication and GitHub Release
creation. Download `cli-package` from the workflow run and inspect:

```text
package/<package-version>.tgz
package/<package-version>.tgz.sha256
cli-release-metadata.json
cli-release/
```

This is the required preflight when introducing or changing Nexus variables.
The build/dry-run job remains on `ubuntu-latest`, so it does not require Nexus
network access or registry variables. It does not prove write permission; the
first real publish must still be observed through the hosted and group
repositories.

`skip_npm` is separate: it skips package publication but can still create a
GitHub Release. Do not combine it with `dry_run` unless only the package
artifact is wanted.

### Local no-publish rehearsal

Before triggering the workflow, a clean local checkout can prove the package
shape without a token or registry write:

```bash
cd cli
bun run lint
bun run typecheck
bun test
bun run build
npm pack --json --pack-destination <temporary-directory>
node dist/index.js version
```

Record the tarball filename, SHA-256, package name/version, and source commit.
Inspect `npm pack --dry-run --json` or the tarball file list for unintended
files. Do not set `NPM_TOKEN` and do not run `npm publish` during this rehearsal.
The GitHub Actions `dry_run` remains the authoritative CI/CD rehearsal because
it also uploads immutable metadata and exercises the workflow job boundaries.

## Verification

After a real release:

```bash
npm view <package>@<version> version --registry <install-registry>
npm install -g <package>@<version> --registry <install-registry>
skillhub version
skillhub help collection
```

Confirm the `npm view` result equals the tag version. The release workflow must
also report that tarballs downloaded independently from the hosted and group
registries both equal the `packageSha256` value in
`cli-release-metadata.json`.

For token rotation, create and test a replacement Nexus token with the same
hosted-write/group-read permissions, update the `NPM_TOKEN` Actions secret,
run a package-only dry run, and revoke the old token only after verification.
Never republish different bytes under an existing version. If group
verification fails after hosted publication, fix Nexus group membership,
content selectors, routing/cache, or read permission and verify the same
immutable version.

## Troubleshooting

### Hosted lookup fails

An authentication, TLS, DNS, or server error is treated as unknown state and
fails the job. Only an explicit not-found response permits publishing.

### Publish succeeds but group verification fails

Check Nexus group membership, content selectors, routing rules, cache state,
and token read permission. Do not rebuild or republish under the same version;
the version and tarball are immutable.

### `403 Forbidden`

Confirm `NPM_TOKEN` has publish permission for the hosted repository and the
configured `NPM_PACKAGE_NAME` scope.

### Publish job does not start

Confirm an online runner has the exact `self-hosted`, `linux`, and
`skillhub-nexus` labels.

### Registry configuration is missing

Set both `NPM_PUBLISH_REGISTRY` and `NPM_INSTALL_REGISTRY`. The workflow does
not fall back to npmjs or a legacy single-registry variable.

### Build or test failure

Reproduce locally:

```bash
make lint-cli
make typecheck-cli
make test-cli
make build-cli
```

## Tag Naming

- CLI releases: `cli-v*` (for example `cli-v0.1.10`)
- Repository releases: `v*` (for example `v0.3.0`)

The namespaces are independent.

# Skill Collections M2 CLI And Nexus Result

Date: 2026-07-27
Milestone: M2 only
Status: complete; stopped before M3

## Source Baseline

- Isolated worktree:
  `C:\Users\USER\projects\skillhub\.worktrees\skill-collections-m0`
- Branch: `codex/skill-collections-m0`
- Local baseline commit:
  `b54a135a674a75202cd30bbc6a5c53510840580c`
- Fetched `upstream/main`:
  `ac46ad53913e413e451710a3563590b62d183927`
- Local `origin/dev` reference:
  `89706c6852476999090a7d0f61cf305674dcc529`
- M0 and M1 remain uncommitted in the same isolated worktree. M2 did not
  alter the original dirty checkout.

## Delivered Contract

The CLI now supports:

```text
skillhub collection install @namespace/collection \
  --registry <SkillHub base URL>
```

`--registry` is mandatory for collection installation. Optional flags are
`--version`, `--scope`, repeatable `--agent`, `--dir`, `--force`, `--token`,
and `--json`.

The implementation:

- strictly validates the `@namespace/collection` coordinate;
- resolves an immutable backend collection manifest;
- validates exact member versions, fingerprints, same-namespace membership,
  unique members, and exact relative download paths;
- reconstructs member downloads against the explicitly configured SkillHub
  registry instead of following a server-provided host;
- preflights every member/target destination before any download;
- downloads and stages all packages before the first destination rename;
- commits all member directories and writes inventory once;
- restores new destinations, forced backups, and the prior inventory in reverse
  order after a commit or inventory failure;
- records exact collection coordinates in member metadata and one normalized
  top-level inventory collection entry;
- preserves collection records through legacy install, list, remove, and
  doctor flows;
- keeps legacy single-skill output and behavior by adapting `installSkill()` to
  the generalized one-package transaction.

Collection update and collection remove commands were not added.

## CLI Files

New runtime files:

- `cli/src/shared/collection-name-parser.ts`
- `cli/src/services/install-transaction.ts`
- `cli/src/services/collection-install-service.ts`
- `cli/src/commands/collection.ts`

Modified runtime files:

- `cli/src/clients/skillhub-client.ts`
- `cli/src/stores/inventory-store.ts`
- `cli/src/services/doctor-service.ts`
- `cli/src/services/install-service.ts`
- `cli/src/commands/install.ts`
- `cli/src/commands/help.ts`
- `cli/src/index.ts`

New tests:

- `cli/test/unit/shared/collection-name-parser.test.ts`
- `cli/test/unit/services/install-transaction.test.ts`
- `cli/test/unit/services/collection-install-service.test.ts`
- `cli/test/unit/commands/collection-command.test.ts`
- `cli/test/unit/scripts/release-workflow.test.ts`
- `cli/test/integration/collection-install-command.test.ts`

Modified test support and regression files:

- `cli/test/helpers/fake-registry.ts`
- `cli/test/unit/clients/skillhub-client.test.ts`
- `cli/test/unit/stores/inventory-store.test.ts`
- `cli/test/unit/services/doctor-service.test.ts`
- `cli/test/unit/services/install-service.test.ts`
- `cli/test/integration/help-command.test.ts`

## TDD Evidence

Observed red states before implementation included:

- missing collection coordinate parser module;
- six missing/invalid collection resolver cases;
- inventory normalization assertions without `collections`;
- missing generalized transaction module;
- legacy two-target installation writing inventory twice;
- missing collection service and command modules;
- nested CAC command options rejected as unknown until command registration was
  corrected;
- fake registry returning `404` before the collection resolve route existed;
- workflow contract missing Nexus hosted/group variables, immutable package
  evidence, and dry-run conditions.

Green coverage includes:

- unsafe coordinates and path traversal rejection;
- response/request coordinate mismatch and cross-namespace rejection;
- duplicate members and forged download path rejection;
- later destination conflict with zero downloads;
- later download and ZIP/staging failures with zero committed destinations;
- all-package staging before the first rename;
- later rename failure removing earlier new installs;
- multi-member `--force` rollback restoring original directories;
- inventory write failure restoring files and the previous inventory;
- injected Windows case-insensitive destination collision;
- legacy inventory normalization;
- legacy install/list/remove/doctor collection-record preservation;
- legacy single-skill install integration without output changes.

## Nexus Release Pipeline

Changed files:

- `.github/workflows/pr-cli.yml`
- `.github/workflows/release-cli.yml`
- `cli/README.md`
- `cli/RELEASE.md`

The release workflow now accepts:

- `NPM_PUBLISH_REGISTRY` repository variable for the hosted repository;
- `NPM_INSTALL_REGISTRY` repository variable for the employee/group
  repository;
- `NPM_PACKAGE_NAME` repository variable for an internal package coordinate;
- legacy `NPM_REGISTRY`, then public npm, as fallbacks;
- `NPM_TOKEN` only as a secret.

`build-and-test` applies the package name and tag version, runs all CLI gates,
calls `npm pack --json` once, computes SHA-256, and writes
`cli-release-metadata.json` with the package identity, source commit, workflow
commit, tarball, and digest. `publish-npm` downloads that artifact without
checking out or rebuilding, publishes the exact tarball to the hosted
repository only when absent, and verifies the exact version through the
install/group repository.

The `dry_run` workflow input still builds, tests, packs, hashes, and uploads the
artifact, but skips registry publication and GitHub Release creation. Existing
`skip_npm` recovery behavior and the public npm default remain available.

The documentation distinguishes:

```text
npx --yes --registry <Nexus npm group> <internal-package>@<version> \
  collection install @opensource/superpowers \
  --registry <SkillHub base URL> --scope user
```

The first registry is consumed by `npx`; the second is consumed by SkillHub
CLI.

No Nexus URL, internal package coordinate, or token was committed. No package
was published and no Nexus write was performed.

## Verification

### CLI

```text
bun run lint
```

Exit `0`.

```text
bun run typecheck
```

Exit `0`. One earlier run found a test tuple inferred as
`string | undefined`; the fixture was made a readonly tuple and the same gate
then passed.

```text
bun test
```

Result: `410 pass`, `6 skip`, `0 fail`, `1116 expect()` calls across 47 files.
The skips are existing Windows symlink cases.

```text
bun run build
node dist/index.js version
```

Exit `0`; output: `SkillHub CLI 0.1.9`.

```text
bun test test/integration/collection-install-command.test.ts
```

Result: `6 pass`, `0 fail`, including legacy cross-command preservation.

The two workflow YAML files also parsed successfully through PyYAML, and the
workflow contract test passed `4 pass`, `0 fail`.

### Python Backend

```text
server-python\.venv\Scripts\python.exe -m pytest tests -q
```

Result: `1006 passed`, `1 warning` in `160.03s`. The warning is the existing
Starlette `httpx` deprecation.

### Frontend

```text
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test
corepack pnpm run build
```

All commands exited `0`. Vitest reported `194 passed` test files and
`691 passed` tests. The production build retained existing warnings for the
runtime-resolved `runtime-config.js` URL and chunks over 500 kB.

### Operator And Architecture Gates

```text
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config --quiet
git diff --check
```

All exited `0`. Docker Compose printed two sandbox permission warnings while
reading `C:\Users\USER\.docker\config.json`; configuration validation still
succeeded. `git diff --check` reported only Windows LF-to-CRLF notices.

This command returned no paths:

```text
git diff --name-only -- \
  server-python/app/api/skills.py \
  server-python/app/repositories/skill_repository.py \
  server-python/app/db/migration
```

Existing skill routes/repositories and the upstream-owned migration baseline
therefore remain outside the collection change.

## Stop Condition And Non-Goals

M2 did not:

- publish the CLI package;
- write to Nexus;
- enable collections in deployment defaults;
- add collection catalog or maintenance UI;
- add UI one-click installation;
- add collection update/remove;
- add GitLab repository import;
- modify scanner behavior;
- add Java, Maven, Spring Boot, or a hybrid runtime;
- stage, commit, push, open a pull request, or deploy.

The next milestone is M3, not part of this result.

# Skill Collections M0-M5 Final Verification

Date: 2026-07-27
Branch: `codex/skill-collections-m0`
Starting commit: `b54a135a674a75202cd30bbc6a5c53510840580c`
Worktree state: intentionally uncommitted

## Outcome

The six approved milestones, M0 through M5, are complete in the isolated local
worktree:

- M0: dormant backend/web/deployment flags and core isolation gates;
- M1: first-class namespace-owned, independently versioned collection backend;
- M2: atomic collection CLI plus Nexus hosted/group CI/CD contract;
- M3: SkillHub-aligned catalog, detail, maintenance, diff, and install UI;
- M4: allowlisted internal GitLab preview/explicit ingest/collection seed;
- M5: curator-triggered immutable SHA update checks, bilingual product and
  operator documentation, local no-publish package rehearsal, and final gates.

No code was committed or pushed. No PR or GitHub Release was created. No
package was published, no real GitLab was contacted, no K8s workload was
changed, and all feature flags remain default off.

## M5 Update Check

`POST /api/web/repository-imports/{import_id}/check-updates` re-authorizes the
stored import and resolves its stored internal GitLab project/ref:

- unchanged SHA returns `changed=false`, downloads no archive, and creates no
  import row;
- changed SHA downloads the bounded archive and creates one immutable preview
  linked by `previous_import_id`;
- prior imports, skill versions, and collection versions remain unchanged;
- new candidates remain unselected and must pass the normal explicit
  ingest/scanner/review/publish/collection workflow;
- namespace MEMBER and disabled-feature behavior remain backend-authoritative.

OpenAPI was regenerated from the running FastAPI app with
`openapi-typescript 7.13.0`; the frontend imports those generated update-check
types.

## Final Verification

Backend:

```powershell
cd server-python
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe scripts\sql_inventory.py
```

Result: `1040 passed`; two known warnings only. SQL inventory reports import
SQL under `app/repository_imports/repository.py` as `repository-query`, with no
new route SQL.

Frontend:

```powershell
cd web
node_modules\.bin\vitest.cmd run
node_modules\.bin\tsc.cmd --noEmit
node_modules\.bin\eslint.cmd . --ext ts,tsx --report-unused-disable-directives --max-warnings 0
node_modules\.bin\vite.cmd build
```

Result: `207` test files and `741` tests passed; typecheck, lint, and build
passed. Build emitted only the existing runtime-config URL and large-chunk
warnings.

Browser vertical flow:

```powershell
node_modules\.bin\playwright.cmd test `
  e2e/collection-catalog.spec.ts `
  e2e/collection-install-command.spec.ts `
  e2e/collection-maintenance.spec.ts `
  e2e/collection-role-access.spec.ts `
  e2e/gitlab-repository-import.spec.ts `
  e2e/collection-gitlab-vertical-flow.spec.ts `
  --project=chromium --workers=1
```

Result: `7 passed`, including curator import → exact collection draft seed →
changed SHA linked preview and MEMBER-hidden controls.

CLI:

```powershell
cd cli
bun run lint
bun run typecheck
bun test
bun run build
node dist/index.js version
```

Result: lint/typecheck/build passed; `410 passed`, `6` existing Windows symlink
skips, `0 failed`, and packed/built CLI reports `0.1.9`.

Documentation:

```powershell
cd docs\skillhub
npm.cmd run build
```

Result: VitePress `1.6.4` rendered the Chinese and English collection guides.
`npm ci` reported three existing dependency audit findings (`1 moderate`,
`2 high`); dependency upgrading was not widened into this feature milestone.

Deployment and image:

```powershell
docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
kubectl kustomize deploy\k8s\base
server-python\.venv\Scripts\python.exe -c "<parse plain backend YAML with PyYAML>"
docker compose --env-file .env.release.example -f compose.release.yml config --quiet
git diff --check
```

Result: Python image built as `skillhub-server-python:verify` (manifest list
`sha256:a69ab7884e183c300a21fbace2d4fa710f5209d2166a599ad5d0b21e2ae3f7f7`);
base render, plain YAML parse, release compose, and diff check passed. Docker
compose emitted only the local unreadable user config warning.

## No-Publish Nexus Rehearsal

The local rehearsal used no token and made no registry write:

```text
package:       @astron-team/skillhub
version:       0.1.9
tarball:       astron-team-skillhub-0.1.9.tgz
bytes:         98137
SHA-256:       26BAD1F0C55990A508EA3EA0C23A3C1CBF9529FC31442E9039D1DE2E8C8B7124
source HEAD:   b54a135a674a75202cd30bbc6a5c53510840580c
source dirty:  true
```

The tarball contains only `LICENSE`, `README.md`, `dist/index.js`, and
`package.json`. The extracted Node artifact returned `SkillHub CLI 0.1.9`.
Because the worktree is dirty by design, this proves package shape and the
no-publish workflow only; it is not an authorized production release artifact.

Local artifact:

```text
C:\Users\USER\projects\skillhub\.worktrees\skill-collections-m0\server-python\.venv\m5-cli-rehearsal-20260727-1426\astron-team-skillhub-0.1.9.tgz
```

## Rollback

Rollback is flag-first and does not drop data:

1. disable web GitLab import;
2. disable backend GitLab import;
3. disable web collections;
4. disable backend collections;
5. revert web/backend/CLI images if necessary.

The additive `local_collection*` and `local_repository_import*` tables remain
as audit/provenance evidence. Existing SkillHub skill, scanner, review, search,
download, namespace, auth, and single-skill CLI paths do not depend on them.

## External Gates Not Executed

These need a later explicit instruction plus organization credentials:

1. publish one immutable internal CLI version to Nexus hosted;
2. verify that exact version/digest through Nexus group;
3. configure and rotate the real GitLab read token and CA/allowlist;
4. deploy to a canary and enable flags in documented order;
5. import one known internal mirror and complete real scanner/review;
6. publish a collection and install it on Windows plus one Unix-like
   workstation;
7. commit, push, or open a PR.

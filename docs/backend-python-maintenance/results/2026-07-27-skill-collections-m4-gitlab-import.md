# Skill Collections M4 Internal GitLab Import Result

Date: 2026-07-27
Branch: `codex/skill-collections-m0`
Starting commit: `b54a135a674a75202cd30bbc6a5c53510840580c`

## Outcome

Milestone 4 is complete in the isolated worktree. SkillHub now has a
default-off, curator-only internal GitLab repository preview and explicit
multi-skill ingest workflow. It reuses the existing Python publish
orchestration and collection draft services; it does not add Java or change
the existing scanner, review, search, download, or single-skill install
contracts.

No request was sent to a real GitLab instance. No package was published, no
deployment was changed, and no feature flag was enabled.

## Delivered Boundaries

- Additive `local_repository_import` and candidate schema in a Python-owned
  local migration.
- Fixed configured HTTPS GitLab origin and allowlisted group prefixes.
- Backend-only token with no redirects, bounded timeouts, optional CA path,
  streamed compressed archive limit, and redacted errors.
- ZIP traversal, absolute path, symlink, duplicate normalized path, file-count,
  per-file-size, and total-expanded-size rejection.
- Independent `SKILL.md` discovery without executing repository content.
- Persisted commit SHA, archive digest, candidate path, actor, and audit
  evidence without token or raw GitLab response persistence.
- Preview does not publish; ingest requires explicit candidate selections.
- Partial ingest results are retryable and already-created versions are not
  republished.
- Collection seeding accepts only the actual exact `PUBLISHED` version rows.
- SkillHub-aligned dialog and cards using existing UI tokens and primitives.
- Namespace MEMBER UI and backend mutation denial.
- Generated OpenAPI TypeScript contracts from the running FastAPI app.
- Base/plain Kubernetes, release compose, environment examples, and operator
  docs with default-off settings.

## Verification

Focused backend:

```powershell
cd server-python
.venv\Scripts\python.exe -m pytest tests -k "repository_import or gitlab_import_client or collection_feature_flags_are_default_off_in_kubernetes" -q
```

Result: `30 passed, 1006 deselected`.

Complete backend:

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

Result: `1036 passed`; two known warnings only (Starlette/httpx deprecation and
the deliberate duplicate-ZIP-entry fixture).

Frontend:

```powershell
cd web
node_modules\.bin\vitest.cmd run
node_modules\.bin\tsc.cmd --noEmit
node_modules\.bin\eslint.cmd . --ext ts,tsx --report-unused-disable-directives --max-warnings 0
node_modules\.bin\vite.cmd build
```

Result: `207` test files and `738` tests passed; typecheck, lint, and build
passed. Vite emitted only the existing runtime-config URL and large-chunk
warnings.

Collection/import browser flow:

```powershell
node_modules\.bin\playwright.cmd test `
  e2e/collection-catalog.spec.ts `
  e2e/collection-install-command.spec.ts `
  e2e/collection-maintenance.spec.ts `
  e2e/collection-role-access.spec.ts `
  e2e/gitlab-repository-import.spec.ts `
  --project=chromium --workers=1
```

Result: `6 passed`.

CLI regression:

```powershell
cd cli
bun run lint
bun run typecheck
bun test
bun run build
bun run src/index.ts version
```

Result: lint/typecheck/build passed; `410 passed`, `6` existing Windows symlink
skips, `0 failed`, and CLI version `0.1.9`.

Operator and repository checks:

```powershell
kubectl kustomize deploy\k8s\base
server-python\.venv\Scripts\python.exe -c "from pathlib import Path; import yaml; paths=[Path('deploy/k8s/plain/backend/config.yaml'),Path('deploy/k8s/plain/backend/deployment.yaml'),Path('deploy/k8s/plain/backend/secret.yaml.example')]; [list(yaml.safe_load_all(p.read_text(encoding='utf-8'))) for p in paths]"
docker compose --env-file .env.release.example -f compose.release.yml config --quiet
server-python\.venv\Scripts\python.exe server-python\scripts\sql_inventory.py
git diff --check
```

Result: base render, plain YAML parse, release compose, SQL inventory, and diff
check passed. Docker printed only the local unreadable user config warning.
Repository-import SQL is classified under `repository-query`; API routes
contain no SQL.

## Rollback

Keep `SKILLHUB_GITLAB_IMPORT_ENABLED=false` and
`SKILLHUB_WEB_GITLAB_IMPORT_ENABLED=false`, or turn both off before reverting
images. The additive local tables remain in place as audit evidence. Collection
and every pre-existing SkillHub function continue independently.

## Remaining Rollout Gates

Milestone 5 must add curator-triggered SHA update checks, product/operator
documentation, and a no-publish Nexus rehearsal. Real Nexus publication,
production/canary deployment, internal GitLab access, and workstation
installation remain external writes that require separate authorization and
environment-specific credentials.

# Follow Upstream v0.2.13

Date: 2026-07-03

## Summary

Upstream `iflytek/skillhub` published app release `v0.2.13` after the local
Python-only fork had already completed `v0.2.12` and `cli-v0.1.8` follow-up.
This is an unhandled upstream app release and needs a focused Python-adapted
follow-up plan. Do not merge or recreate Java/Spring files; use the upstream
Java changes only as behavior evidence.

## Upstream Release Evidence

- Release/tag: `v0.2.13`
- Release URL: <https://github.com/iflytek/skillhub/releases/tag/v0.2.13>
- Published at: `2026-07-03T08:24:54Z`
- Tag commit: `e32f05b375379d887bd3766b40f993c70d39db54`
- Tag URL: <https://github.com/iflytek/skillhub/tree/v0.2.13>
- Previous app baseline: `v0.2.12`
- Full changelog: <https://github.com/iflytek/skillhub/compare/v0.2.12...v0.2.13>

Commands used:

```powershell
curl.exe -sS -H "Accept: application/vnd.github+json" -H "User-Agent: codex-skillhub-release-watch" https://api.github.com/repos/iflytek/skillhub/releases/latest
curl.exe -sS -H "Accept: application/vnd.github+json" -H "User-Agent: codex-skillhub-release-watch" https://api.github.com/repos/iflytek/skillhub/tags?per_page=20
git ls-remote --tags https://github.com/iflytek/skillhub.git
git fetch upstream --tags --prune
git show --no-patch --decorate --oneline v0.2.13
git log --oneline v0.2.12..v0.2.13
git diff --name-status v0.2.12..v0.2.13
git diff --stat v0.2.12..v0.2.13
```

Relevant upstream commits:

- `78b8b34e chore(cli): bump version to 0.1.8`
- `665ee049 feat(auth): add ISSUE-60 password capability field`
- `54006e72 fix(web): ISSUE-62 gate security settings by capability`
- `9f927c12 fix(PR): default deny security password changes`
- `e501be9c feat(promotion): improve promotion review dashboard`
- `0134da73 fix(frontend): support nested preview links`
- `bf7c71ad fix(scanner): backport local LLM base URL handling for #563`
- `db8aa36f fix(frontend): patch undici alerts and harden staging web`
- `3a254d75 fix(auth): guard SUPER_ADMIN role mutations`

## Local Baseline Evidence

- `AGENTS.md` says this branch is a full-Python backend project; the old Java
  `server/` runtime has been removed and must not be reintroduced.
- `CLAUDE.md` is not present in the repo root.
- Current branch was clean before plan creation: `## dev...origin/dev`.
- Local app release baseline:
  `docs/backend-python-maintenance/results/2026-06-20-v0.2.12-intake.md`
  records `v0.2.12` as completed for applicable Python behavior and contracts.
- Local CLI release baseline:
  `docs/backend-python-maintenance/results/2026-07-01-cli-v0.1.8-follow-up.md`
  records `cli-v0.1.8` as completed and CLI-only.
- `deploy/k8s/README.md` documents the Python cutover runtime and deployment of
  only `skillhub-web`, `skillhub-server`, and `skillhub-scanner`.

## Gap Summary

| Area | Upstream `v0.2.13` change | Local Python follow-up |
| --- | --- | --- |
| Backend Python auth/API | `/api/v1/auth/me` now exposes backend-authoritative `canChangePassword`, based on whether a local credential exists. | Add a Python `canChangePassword` field to auth-me responses, OpenAPI/schema generation, and tests for local-password, OAuth/session, bearer, and mock-user paths. Default deny when the credential state cannot be proven. |
| Backend Python role security | Non-`SUPER_ADMIN` actors cannot assign `SUPER_ADMIN` or replace an existing `SUPER_ADMIN` user's role with another role. | Harden `server-python/app/admin/user_repository.py` so existing `SUPER_ADMIN` role state is protected from non-super-admin mutation, not only assignment. Add repository and route tests. |
| Backend Python promotion API | Promotion responses include richer source skill metadata; history supports reviewed-time sorting; pending lists use stable newest-first ordering and stricter status/sort validation. | Extend Python promotion query/response contracts, validation, and ordering while preserving existing transaction/audit behavior. Add tests for pending order, approved/rejected `reviewedAt` asc/desc, invalid sort/status, and new metadata fields. |
| Schema/migration | Upstream diff does not add a DB migration in `v0.2.12..v0.2.13`; fields are derived from existing tables. | Prefer query joins over schema changes. If implementation proves a column/index is missing in Python, stop and write a separate migration plan before editing schema. |
| Frontend/API contract | Generated API types include `canChangePassword` and richer promotion fields. Security settings page is gated by capability. Promotion dashboard has richer cards and history sorting. | Regenerate/update OpenAPI-derived types through the repo's normal generation path, then adapt web code/tests using TanStack Query patterns. Do not manually edit generated files. |
| Skill package preview | Nested relative markdown links inside package preview dialogs resolve correctly. | Compare against existing `package-relative-link` and file-preview code; port only missing nested-link behavior and add a focused test. |
| Scanner | Upstream pins scanner package version and applies a `cisco-ai-skill-scanner` `1.0.2` local LLM base URL backport in the scanner image. | Local K8s already exposes `SKILL_SCANNER_LLM_BASE_URL`; evaluate and port the scanner Dockerfile/backport script or equivalent only if the packaged scanner still drops local LLM base URL. Add a build-level or script-level regression test. |
| CLI | Upstream range includes `cli-v0.1.8`, but local CLI metadata already followed it. | No CLI version bump expected. Re-run targeted CLI verification only if generated API contracts force CLI changes. |
| Deployment/K8s | Upstream documents scanner LLM base URL/model settings and adds scanner env wiring. | Keep Python deployment ergonomics. Confirm base and plain manifests, secret examples, and Chinese env manual consistently expose scanner LLM base URL/model. |
| Documentation | Auth/API docs, scanner guides, Kubernetes docs, and security-scanning docs changed. | Update Python-maintained operator/product docs to match the implemented Python behavior after each verified phase. |
| Tests/verification | Upstream adds focused backend, frontend, Playwright, and scanner regression coverage. | Add Python and TypeScript tests before or alongside implementation, then run the commands below. |

## Implementation Phases

### Phase 1: Auth Capability And Security Settings

Goal: expose and consume `canChangePassword` safely.

Steps:

1. Add Python tests for `/api/v1/auth/me` proving local-password users get
   `canChangePassword: true`, OAuth-only or credentialless users get `false`,
   and uncertain paths default to `false`.
2. Implement credential-backed capability assembly in Python auth code without
   changing session or bearer precedence.
3. Regenerate or update API types through the existing generated-file workflow.
4. Gate `web/src/pages/settings/security.tsx` on the capability and show the
   unavailable state for accounts that cannot change a local password.

Verify:

```powershell
cd server-python
uv run pytest tests/test_auth_me.py tests/test_session_auth.py tests/test_oauth_flow.py tests/test_local_auth_core.py -q

cd ..\web
corepack pnpm exec vitest run src/pages/settings/security.test.tsx src/shared/components/user-menu.test.tsx
corepack pnpm run typecheck
```

Success criteria:

- The auth-me response contract includes `canChangePassword`.
- Security settings no longer offers local password changes to OAuth-only or
  credentialless users.
- Existing local-password change flows still pass.

### Phase 2: SUPER_ADMIN Role Mutation Guard

Goal: prevent non-super-admin users from removing or replacing an existing
`SUPER_ADMIN` role.

Steps:

1. Add repository tests for non-super-admin attempts to assign `SUPER_ADMIN`,
   replace an existing `SUPER_ADMIN` with `USER`, and replace an existing
   `SUPER_ADMIN` with another platform role.
2. Add route tests proving the same behavior through
   `/api/v1/admin/users/{userId}/roles`.
3. Update `server-python/app/admin/user_repository.py` to read the target's
   current role state inside the mutation transaction before deleting bindings.

Verify:

```powershell
cd server-python
uv run pytest tests/test_admin_user_management.py -q
uv run pytest tests/test_route_policy_enforcement.py tests/test_admin_user_management.py -q
```

Success criteria:

- Only actors with `SUPER_ADMIN` can mutate users who currently hold
  `SUPER_ADMIN`.
- `USER_ADMIN` retains existing non-super-admin user role-management behavior.

### Phase 3: Promotion Review Contract And Dashboard

Goal: follow upstream promotion-review usability improvements without changing
Python deployment architecture.

Steps:

1. Add Python tests for promotion list response metadata:
   `sourceSkillDisplayName`, `sourceSkillSummary`, source version file count,
   source version total size, source skill download count, and source skill
   star count where existing tables support them.
2. Add Python tests for pending newest-first ordering, approved/rejected
   `reviewedAt` sorting, default history sort, and invalid status/sort
   handling.
3. Update promotion query/repository code and route parameters.
4. Update web promotion hooks, dashboard screen, i18n, and tests to consume the
   richer contract and sorting.

Verify:

```powershell
cd server-python
uv run pytest tests/test_promotion_read.py tests/test_promotion_write.py -q

cd ..\web
corepack pnpm exec vitest run src/features/promotion/use-promotion-list.test.ts src/pages/dashboard/promotions.test.tsx
corepack pnpm run typecheck
corepack pnpm run lint
```

Success criteria:

- Promotion reviewers can distinguish pending items using richer source skill
  metadata.
- Reviewed history sorting behaves deterministically.
- Existing approve/reject audit and notification behavior remains stable.

### Phase 4: Package Preview And Frontend Dependency Security

Goal: port frontend fixes that apply to the Python fork.

Steps:

1. Add/adjust tests for nested relative links in markdown package preview.
2. Port the link handling change only where current package preview behavior is
   missing it.
3. Review the upstream `undici` lockfile patch against this repo's current
   `web/pnpm-lock.yaml`; apply only the necessary dependency resolution update
   using pnpm, not manual lockfile editing.

Verify:

```powershell
cd web
corepack pnpm exec vitest run src/pages/skill-detail.test.tsx src/features/skill/package-relative-link.test.ts src/features/skill/file-preview-dialog.test.ts
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test
```

Success criteria:

- Nested package markdown links resolve to the intended package files.
- Dependency/security lockfile changes are tool-generated and tests still pass.

### Phase 5: Scanner And Deployment Docs

Goal: keep scanner local LLM configuration working in Python deployment paths.

Steps:

1. Add a regression check for scanner image handling of
   `SKILL_SCANNER_LLM_BASE_URL`, based on upstream
   `scripts/tests/scanner-llm-base-url-test.sh` but adapted for Windows/this
   repo if needed.
2. Pin or document the scanner package version and apply the upstream backport
   only if needed to preserve local LLM base URL behavior.
3. Confirm `deploy/k8s/base`, `deploy/k8s/plain`, `deploy/k8s/README.md`, and
   `deploy/k8s/environment-variables.zh.md` consistently describe scanner LLM
   base URL/model settings.

Verify:

```powershell
docker build -t skillhub-scanner:verify -f scanner/Dockerfile scanner
kubectl kustomize deploy\k8s\base
kubectl kustomize deploy\k8s\overlays\external
docker compose --env-file .env.release.example -f compose.release.yml config
```

Success criteria:

- Scanner deployments can pass LLM base URL/model into the scanner container.
- No Java/Spring runtime assumptions are introduced.

### Phase 6: Final Verification And Result Note

Goal: prove the Python-only fork has followed applicable `v0.2.13` behavior.

Steps:

1. Run backend, web, scanner/deployment, and whitespace checks.
2. Write a result note under
   `docs/backend-python-maintenance/results/YYYY-MM-DD-v0.2.13-follow-up.md`
   with commands, results, decisions, and non-goals.
3. Leave commit/PR work for a separate explicit user instruction.

Verify:

```powershell
cd server-python
uv run pytest tests -q

cd ..\web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test
corepack pnpm run build

cd ..
docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
docker build -t skillhub-scanner:verify -f scanner/Dockerfile scanner
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check
```

Success criteria:

- All relevant tests/checks pass or any blocker is recorded with exact output.
- A maintenance result note records the completed `v0.2.13` follow-up.

## Documentation To Update

- `docs/backend-python-maintenance/results/YYYY-MM-DD-v0.2.13-follow-up.md`
- `docs/03-authentication-design.md`
- `docs/06-api-design.md`
- `deploy/k8s/README.md`
- `deploy/k8s/environment-variables.zh.md`
- `docs/security-scanning.md`
- `docs/skillhub/guide/kubernetes.md`
- `docs/skillhub/guide/scanner.md`
- `docs/skillhub/en/guide/kubernetes.md`
- `docs/skillhub/en/guide/scanner.md`
- Any web docs or generated OpenAPI docs affected by `canChangePassword` or
  promotion response fields.

## Explicit Non-Goals

- Do not reintroduce Java, Maven, Spring Boot, or a hybrid runtime.
- Do not copy upstream `server/` files into this branch.
- Do not manually edit generated OpenAPI files; use the repo generation path.
- Do not implement unrelated cleanup or refactors.
- Do not change schema unless a separate migration plan is written first.
- Do not change CLI package metadata unless a new CLI release/tag appears.
- Do not commit, push, or open a PR during plan execution unless explicitly
  requested later.

## Paste-Ready Execution Prompt

```text
Follow the plan in docs/backend-python-maintenance/plans/2026-07-03-follow-upstream-v0.2.13.md.

Workspace: C:\Users\USER\OneDrive\Documents\skillhub. Follow AGENTS.md and treat this repo as a full-Python backend project. Do not reintroduce Java, Maven, Spring Boot, or a hybrid runtime. Do not manually edit generated files; use the repo generation workflow. Write tests before or alongside code changes.

Implement the upstream v0.2.13 follow-up in phases:
1. Add backend-auth `canChangePassword` support and gate the security settings UI.
2. Harden SUPER_ADMIN role mutation protection.
3. Port promotion review response metadata, sorting, validation, and dashboard updates.
4. Port nested markdown preview link behavior and applicable frontend dependency security update.
5. Adapt scanner local LLM base URL/backport and deployment docs only where needed.
6. Run the required backend, web, scanner/deployment, and whitespace checks, then write docs/backend-python-maintenance/results/YYYY-MM-DD-v0.2.13-follow-up.md with exact commands/results.

Keep changes surgical. Preserve existing Python cutover decisions and deployment ergonomics unless upstream v0.2.13 changed a public contract. Do not commit, push, or open a PR unless explicitly instructed after verification.
```

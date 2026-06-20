# v0.2.12 Upstream Follow-Up Plan

Date: 2026-06-20

## Goal

Bring the Python-only SkillHub fork from the stable
`python-upstream-v0.2.11-stable` baseline up to upstream `iflytek/skillhub`
`v0.2.12`, without reintroducing Java or hybrid runtime assumptions.

## Upstream Release Evidence

- GitHub release: `v0.2.12`
- Release URL: <https://github.com/iflytek/skillhub/releases/tag/v0.2.12>
- Published at: `2026-06-18T07:51:47Z`
- Upstream tag commit: `f8ea4e67e44b0ba262c926e4149aceb0ad52ef4c`
- Release highlights:
  - anonymous public CLI search/install with installability filtering
  - invalid CLI bearer tokens fail closed
  - AgentGuard builtin skill
  - notification reliability for SSE/profile reviews/promotion/publish events
  - promotion self-review parity for `SUPER_ADMIN`
  - runtime/release/archive/workflow/security hardening

Commands used to recheck scope:

```powershell
git fetch upstream --tags --prune
git log --oneline v0.2.11..v0.2.12
git diff --name-status v0.2.11..v0.2.12
git diff --stat v0.2.11..v0.2.12
```

## Local Baseline Evidence

- Current branch: `dev`
- Current local stable tag: `python-upstream-v0.2.11-stable`
- Stable tag commit: `b51ccad5`
- Existing upstream tag `v0.2.11` is preserved as the original upstream Java
  release tag, not the Python fork baseline.
- Python backend runtime is the owner of backend behavior:
  - `server-python/app`
  - `server-python/tests`
  - `deploy/k8s`
- The old Java `server/` tree is intentionally absent from the active Python
  branch.

## Intake Conclusion

`v0.2.12` is a real upstream app release with Python-impacting behavior. We
should not merge it file-for-file, because most upstream backend changes are in
Java. The correct approach is to port the behavior and contracts into the
Python backend, then adapt CLI/frontend/docs/release-path changes that still
apply to this fork.

The main implementation work is not schema-heavy. No new upstream Flyway
migration appears in `v0.2.11..v0.2.12`, so this should remain a behavior,
contract, security, and docs follow-up unless tests prove a Python schema gap.

## Release Item Classification

| Upstream area | Local action | Notes |
| --- | --- | --- |
| CLI anonymous public search/install | Port now | Requires Python `/api/cli/v1/skills/*` behavior and CLI client tests together. |
| Invalid CLI bearer fail-closed | Port now | Python auth already has bearer support, but CLI routes need explicit invalid-token tests. |
| Installability filtering before pagination | Port now | Search must filter to installable latest versions before applying page/limit. |
| Restricted anonymous resolve/download | Port now | Anonymous CLI resolve/download should cleanly reject non-public/non-installable versions. |
| CLI interactive Enter selection | Port now | Direct TypeScript CLI change; no Python dependency. |
| CLI bounded downloads/archive hardening | Port now | Direct TypeScript CLI hardening; verify install still works. |
| Atomic CLI install directory writes | Port now | Direct TypeScript CLI hardening; affects install flow. |
| Super-admin self promotion review | Port now | Python `promotion.workflow` currently rejects all self review. |
| Profile review notifications | Port with adaptation | Python has admin profile review routes; add event/fanout semantics if missing. |
| Publish notification owner/promotion reviewer fix | Port with adaptation | Compare Python notification recipient rules before changing. |
| SSE media/header keepalive behavior | Audit then port | Python SSE exists; only port if route/headers/live push differ. |
| AgentGuard builtin manifest | Port now | Update Python builtin manifest and bootstrap tests. |
| Release/runtime secret hardening | Port with adaptation | Adopt shell/config checks that still apply to Python release path. |
| Java-only CI/backend changes | Non-goal | Do not reintroduce Java, Maven, Spring, or Java workflow assumptions. |
| Docs/dependency refresh | Docs-only/adapt | Update only docs that reflect Python runtime or CLI behavior changes. |

## Recommended Milestones

### Milestone 1: Intake Result And Branch Hygiene

Goal: create a current result note that records the exact `v0.2.12` triage from
the Python baseline.

Files:

- Create: `docs/backend-python-maintenance/results/2026-06-20-v0.2.12-intake.md`
- Modify: `docs/backend-python-maintenance/plans/2026-06-19-follow-upstream-v0.2.12.md`

Steps:

1. Record release evidence, local baseline, and classification table.
2. Confirm no Java runtime files are reintroduced.
3. Confirm whether `docs/backend-python-maintenance/plans/2026-06-19-follow-upstream-v0.2.12.md`
   should be tracked in the next commit.

Verify:

```powershell
git diff --name-status v0.2.11..v0.2.12
git log --oneline v0.2.11..v0.2.12
git status --short --branch
```

Success criteria:

- Intake note clearly distinguishes upstream `v0.2.12` from local
  `python-upstream-v0.2.11-stable`.
- Every upstream release highlight is classified as `port-now`,
  `port-with-adaptation`, `docs-only`, `already-covered`, or `non-goal`.

### Milestone 2: Python CLI API Public Installability And Bearer Hardening

Goal: make the Python `/api/cli/v1/skills/*` API match upstream anonymous
public install/search semantics and invalid-bearer fail-closed behavior.

Likely files:

- Modify: `server-python/app/api/skills.py`
- Modify: `server-python/app/auth/context.py`
- Modify: `server-python/app/skills/read_repository.py`
- Modify: `server-python/app/skills/read_resolve.py`
- Modify: `server-python/app/skills/read_files.py`
- Test: `server-python/tests/test_cli_skills.py`
- Test: `server-python/tests/test_auth_bearer.py`
- Test: `server-python/tests/test_skill_resolve.py`
- Test: `server-python/tests/test_skill_download.py`

Behavior to port:

- Anonymous CLI search returns only public, published, download-ready,
  non-yanked installable results.
- Installability filtering happens before pagination/limit.
- Authenticated bearer search still sees allowed private/namespace results
  according to token/user visibility.
- Invalid bearer token on CLI search/resolve/download returns 401 and must not
  fall back to anonymous visibility.
- Anonymous restricted resolve/download returns a clean 4xx contract, not a
  partial installable response.

Verify:

```powershell
cd server-python
uv run pytest tests\test_cli_skills.py tests\test_auth_bearer.py tests\test_skill_resolve.py tests\test_skill_download.py -q
```

Success criteria:

- New tests fail before implementation and pass after the Python port.
- Existing mock/session auth behavior remains unchanged.
- CLI search totals and items reflect post-filter installable results.

### Milestone 3: TypeScript CLI Client Hardening

Goal: port upstream CLI-side 0.2.12 changes that are independent of Java.

Likely files:

- Modify: `cli/src/index.ts`
- Modify: `cli/src/commands/help.ts`
- Modify: `cli/src/agents/resolver.ts`
- Modify: `cli/src/platform/archive.ts`
- Create: `cli/src/platform/download.ts`
- Modify: `cli/src/services/install-service.ts`
- Test: `cli/test/integration/search-command.test.ts`
- Test: `cli/test/integration/install-command.test.ts`
- Test: `cli/test/unit/agents/resolver-interactive.test.ts`
- Test: `cli/test/unit/platform/archive.test.ts`
- Test: `cli/test/unit/services/install-service.test.ts`

Behavior to port:

- `skillhub search` accepts `--token`.
- Interactive install target selection treats Enter on the highlighted option as
  a selection.
- Downloads are bounded by maximum package size.
- Zip extraction rejects zip64, multidisk, too many entries, oversized entries,
  oversized total uncompressed data, and path traversal.
- Install extracts to a temp directory and atomically moves into place.

Verify:

```powershell
cd cli
bun run typecheck
bun run lint
bun test test\integration\search-command.test.ts test\integration\install-command.test.ts test\unit\agents\resolver-interactive.test.ts test\unit\platform\archive.test.ts test\unit\services\install-service.test.ts
bun run test
```

Success criteria:

- CLI tests pass on Windows. Symlink-specific doctor tests may skip when the OS
  lacks symlink permissions, but no test may fail.
- Existing publish/install/search behavior remains compatible with the Python
  API.

### Milestone 4: Promotion Review Parity

Goal: allow `SUPER_ADMIN` users to review their own promotion requests while
still rejecting self-review for `SKILL_ADMIN`.

Likely files:

- Modify: `server-python/app/promotion/workflow.py`
- Test: `server-python/tests/test_promotion_write.py`
- Test: `server-python/tests/test_promotion_read.py`
- Test: `server-python/tests/test_route_policy_enforcement.py`

Behavior to port:

- If `submitted_by == reviewer_id`, allow approval/rejection only when platform
  roles include `SUPER_ADMIN`.
- Audit details should record self-review when applicable.
- Existing non-self `SKILL_ADMIN`/`SUPER_ADMIN` review remains valid.
- Existing owner-only or ordinary user denial remains valid.

Verify:

```powershell
cd server-python
uv run pytest tests\test_promotion_write.py tests\test_promotion_read.py tests\test_route_policy_enforcement.py -q
```

Success criteria:

- Super-admin self approval/rejection passes.
- Skill-admin self approval/rejection still returns 403.
- Promotion audit and response shapes remain Java-compatible.

### Milestone 5: Notifications And Builtin Manifest

Goal: port the notification reliability behavior that matters to the Python
runtime and refresh builtin skills for AgentGuard.

Likely files:

- Modify: `server-python/app/api/notifications.py`
- Modify: `server-python/app/notifications.py`
- Modify: `server-python/app/admin/review_reports.py`
- Modify: `server-python/app/promotion/workflow.py`
- Modify: `server-python/app/builtin_skills/manifest.json`
- Test: `server-python/tests/test_notification_sse.py`
- Test: `server-python/tests/test_notification_sse_fanout.py`
- Test: `server-python/tests/test_notifications.py`
- Test: `server-python/tests/test_admin_review_report_mutations.py`
- Test: `server-python/tests/test_builtin_skills.py`

Behavior to audit/port:

- SSE route returns/keeps `text/event-stream` behavior and remains open.
- Profile review submission notifies `USER_ADMIN` and `SUPER_ADMIN` users.
- Publish notifications are sent only to the intended owner recipient and do
  not notify promotion reviewers incorrectly.
- Promotion approval/rejection notifications use the correct recipient set.
- Builtin manifest includes upstream AgentGuard and remains idempotent.

Verify:

```powershell
cd server-python
uv run pytest tests\test_notification_sse.py tests\test_notification_sse_fanout.py tests\test_notifications.py tests\test_admin_review_report_mutations.py tests\test_promotion_write.py tests\test_builtin_skills.py -q
```

Success criteria:

- Notification recipient tests prove no duplicate or wrong-recipient fanout.
- SSE tests prove live stream behavior and expected headers.
- Builtin sync tests prove AgentGuard can be imported safely.

### Milestone 6: Release Path, Frontend Contract, And Docs

Goal: adapt upstream hardening and docs changes that still apply to the
Python-only release/deployment path.

Likely files:

- Modify: `.env.release.example`
- Modify: `compose.release.yml`
- Modify: `docker-compose.staging.yml`
- Modify: `scripts/runtime.sh`
- Modify: `scripts/validate-release-config.sh`
- Create/modify: `scripts/tests/*.sh` where applicable
- Modify: `web/e2e/helpers/session.ts`
- Create/modify: `web/e2e/helpers/csrf.ts` if current web tests require it
- Modify: `web/src/app/router.tsx`
- Modify: `web/vite.config.ts`
- Modify: `cli/README.md`
- Modify: `deploy/k8s/environment-variables.zh.md` only if Python env behavior changes
- Modify: `docs/backend-python-maintenance/results/2026-06-20-v0.2.12-final.md`

Behavior to port/adapt:

- Runtime secret validation that applies to Python containers.
- Release config validation that applies to Python compose/K8s usage.
- Frontend route/test assumptions from upstream only where Python API contracts
  changed.
- CLI docs for anonymous public search/install and `--token`.

Verify:

```powershell
cd web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm exec playwright test e2e\public-skill-detail-anonymous.spec.ts e2e\reviews-pagination.spec.ts e2e\skill-subscription.spec.ts --project=chromium

cd ..\server-python
uv run pytest tests -q

cd ..
docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check
```

Success criteria:

- Frontend and backend contract tests pass against the Python backend.
- Release docs still describe only frontend/backend/scanner deployments.
- No Java/Maven/Spring runtime assumptions are reintroduced.

## Final Verification Gate

Before declaring `v0.2.12` followed, run:

```powershell
cd server-python
uv run pytest tests -q

cd ..\cli
bun run typecheck
bun run lint
bun run test

cd ..\web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test:e2e:smoke
corepack pnpm exec playwright test e2e\public-skill-detail-anonymous.spec.ts e2e\publish-flow-ui.spec.ts e2e\namespace-review-detail-access.spec.ts e2e\skill-subscription.spec.ts --project=chromium

cd ..
docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check
```

## Explicit Non-Goals

- Do not reintroduce Java, Maven, Spring Boot, or hybrid runtime paths.
- Do not port upstream Java internals file-for-file.
- Do not blindly mirror upstream CI jobs that only test Java modules.
- Do not broaden this into unrelated ORM/native-SQL refactors.
- Do not overwrite upstream tag `v0.2.12`; if a Python stable point is needed,
  use a separate tag such as `python-upstream-v0.2.12-stable`.

## Paste-Ready Prompt For Execution

```text
Work in C:\Users\USER\OneDrive\Documents\skillhub.

Execute docs/backend-python-maintenance/plans/2026-06-19-follow-upstream-v0.2.12.md.

Baseline:
- Current Python stable tag: python-upstream-v0.2.11-stable
- Upstream release to follow: iflytek/skillhub v0.2.12
- Do not reintroduce Java, Maven, Spring Boot, or hybrid runtime assumptions.

Rules:
- Use tests first or alongside every behavior change.
- Keep changes scoped to v0.2.12 parity.
- Persist result notes under docs/backend-python-maintenance/results/.
- Commit/push only when explicitly approved.

Milestone order:
1. Intake result and branch hygiene.
2. Python CLI API public installability and bearer hardening.
3. TypeScript CLI client hardening.
4. Promotion review parity.
5. Notifications and builtin manifest.
6. Release path, frontend contract, and docs.

Final gate:
Run backend full pytest, CLI typecheck/lint/test, web typecheck/lint/E2E smoke,
docker build, kubectl kustomize, compose config, and git diff --check.
```

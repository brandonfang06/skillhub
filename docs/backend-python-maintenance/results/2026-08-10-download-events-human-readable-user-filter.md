# Download Events Human-Readable User Filter Result

**Date:** 2026-08-10

**Branch:** `codex/download-events-user-filter`

**Worktree:** `C:\Users\USER\projects\skillhub\.worktrees\download-events-user-filter`

**Baseline:** `0abff8c87afd901a9f626f23a516204f6e6469cb`

**Integration target:** `origin/dev` by verified fast-forward

## Outcome

The platform-admin Download Events list and CSV export now accept
`userQuery`, a case-insensitive literal substring filter over OAuth display
name or stable user ID. The old exact `userId` API parameter remains supported.
The page renders display name first and the ID beneath it in monospace, with ID
and anonymous fallbacks. No OAuth claim, environment variable, schema,
scanner, CLI, or deployment-manifest change was required.

PostgreSQL wildcard characters `%` and `_` are escaped and therefore do not
silently broaden the query.

## TDD Evidence

- Backend RED: 2 expected failures before `userQuery` was accepted; the
  route ignored the query and the repository rejected `user_query`.
- Backend wildcard RED: 1 expected failure before literal `LIKE` escaping.
- Backend GREEN: `15 passed` in `tests/test_download_analytics.py`.
- Frontend transport RED: 5 expected failures before the API, route state, and
  page carried `userQuery`.
- UI RED: 3 expected failures before readable ordering and locale keys.
- Frontend GREEN: `204 passed` test files, `810 passed` tests.

## Automated Verification

| Command | Result |
| --- | --- |
| `uv run pytest tests -q` | `1225 passed, 5 skipped`; one existing Starlette/httpx deprecation warning |
| `corepack pnpm run typecheck` | exit 0 |
| `corepack pnpm run lint` | exit 0, zero warnings |
| `corepack pnpm test` | `204` files and `810` tests passed; existing jsdom navigation notice |
| `corepack pnpm run build` | exit 0; existing runtime-config, Browserslist, and chunk-size notices |
| `playwright test -c playwright.subpath.config.ts` | `20 passed` across desktop and mobile Chromium |
| `docker build -t skillhub-download-events-server:verify -f server-python/Dockerfile .` | exit 0 |
| `kubectl kustomize deploy\k8s\base` | exit 0 |
| `docker compose --env-file .env.release.example -f compose.release.yml config` | exit 0 |
| `git diff --check` | exit 0 |

The final pre-push rerun again produced backend `1225 passed, 5 skipped`,
frontend `204` files / `810` tests, typecheck, lint, production build, and
subpath Playwright `20 passed`. One frontend run performed concurrently with
the full backend suite lost a Vitest fork worker after `203` files / `808`
tests; the identical frontend command passed completely when rerun alone,
confirming resource contention rather than an assertion failure.

A targeted Ruff audit reproduced the same import-order, forward-annotation,
and existing date-parsing findings against the untouched `HEAD` versions of
the two files. Those pre-existing items were not broadened into this feature.

The live FastAPI OpenAPI document exposes optional `userQuery` on both admin
list and CSV operations. The repository's existing `generate-api` command
still targets the removed Java-era `/v3/api-docs`; replacing the entire
generated schema from FastAPI would rewrite unrelated surfaces. That
pre-existing generator cutover debt was not bundled into this narrow change.

## Real-Service Verification

An isolated `skillhub-download-events` stack ran PostgreSQL 16, Redis 7,
MinIO, and the Python scanner as healthy services. Python migration upgrade
completed at baseline `skillhub_flyway_v43_baseline`. FastAPI and web were then
connected to that stack; no mock database was used for the runtime checks.

OAuth-like PostgreSQL fixtures included two users named `Alex Chen`, one
different user, identity bindings, and three download events. Authenticated
JSON and CSV assertions produced:

```text
NameQueryTotal: 2
NameQueryIds: verify-oauth-a,verify-oauth-b
IdFragment: verify-oauth-b
ExactUserId: verify-oauth-a
CombinedAndTotal: 0
CsvRows: 2
CsvIds: verify-oauth-a,verify-oauth-b
LiteralPercentTotal: 0
LiteralUnderscoreTotal: 0
```

The root Vite path and a production-built Nginx web image behind the canonical
`/skillhub` prefix were both exercised in a real browser. Desktop and 390 px
mobile checks showed `Alex Chen` first, the stable ID second, two same-name
rows, no horizontal overflow, no console errors, and a successful CSV download.
The subpath CSV URL remained prefixed:

```text
/skillhub/api/v1/admin/download-events.csv?userQuery=Alex+Chen
```

Acceptance services remain available at:

- Root: `http://download-events.localhost:3100/admin/download-events`
- `/skillhub`: `http://download-events-subpath.localhost:3101/skillhub/admin/download-events`
- Final-code direct backend: `http://127.0.0.1:8082`

The isolated test rows and service volume were intentionally retained for user
acceptance. Verification was completed before integration; no pull request was
required for the user-approved direct fast-forward to `dev`.

## Final Review

The final diff was reviewed against both the repository standards and the
approved design. SQL remains inside the Python repository layer, the FastAPI
routes only bind transport parameters, TanStack Query and base-path-aware URL
building remain intact, all three locales are covered, and the old exact
`userId` contract is preserved. No blocking correctness, security,
authorization, deployment, or spec findings remain. The full generated
OpenAPI TypeScript cutover is the only recorded pre-existing follow-up and is
not required for this endpoint's hand-written client contract.

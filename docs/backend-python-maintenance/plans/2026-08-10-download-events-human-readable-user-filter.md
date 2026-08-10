# Download Events Human-Readable User Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let platform administrators filter Download Events by readable OAuth display name or user ID while retaining exact-ID compatibility and audit clarity.

**Architecture:** Add an optional `userQuery` transport parameter to the two admin read endpoints and pass it into the existing Python repository. The repository applies one bound, case-insensitive substring predicate to the joined user display name or event user ID. The React page sends the new parameter, keeps legacy route input compatible, and renders the readable name before the stable ID.

**Tech Stack:** FastAPI, async SQLAlchemy text queries, PostgreSQL, pytest, React 19, TypeScript, TanStack Query/Router, Vitest, i18next, Docker Compose, Nginx, Playwright.

---

### Task 1: Add the backend user-query contract with TDD

**Files:**
- Modify: `server-python/tests/test_download_analytics.py`
- Modify: `server-python/app/download_analytics/repository.py`
- Modify: `server-python/app/api/download_analytics.py`

- [x] **Step 1: Write failing repository and route tests**

Add tests that call `list_admin_download_events(..., user_query=" user a ")`,
assert the normalized bound value is `%user a%`, assert the SQL count query
joins `user_account`, and assert matching by either display name or user ID.
Add a route test using `userQuery=User A` and a CSV route test that proves the
same parameter reaches the repository. Retain an exact `user_id="user-a"`
assertion.

- [x] **Step 2: Run the focused backend test and verify RED**

```powershell
cd server-python
uv run pytest tests/test_download_analytics.py -q
```

Expected: the new tests fail because the route and repository functions do not
accept `userQuery` / `user_query` and the count query lacks the required join.

- [x] **Step 3: Implement the minimal backend behavior**

In `repository.py`, add `user_query: str | None` to the admin list/export and
shared list/CSV read path. Extend `_where_clause` with a normalized parameter:

```python
filters.append(
    "(LOWER(COALESCE(ua.display_name, '')) LIKE :user_query ESCAPE '!' "
    "OR LOWER(COALESCE(de.user_id, '')) LIKE :user_query ESCAPE '!')"
)
escaped_value = value.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
params["user_query"] = f"%{escaped_value}%"
```

Use `LEFT JOIN user_account ua ON ua.id = de.user_id` in the count query as
well as the row/CSV queries. Keep `de.user_id = :user_id` unchanged for exact
compatibility. In `download_analytics.py`, bind optional `userQuery` on only the
two admin endpoints and pass it through.

- [x] **Step 4: Run the focused backend test and verify GREEN**

```powershell
cd server-python
uv run pytest tests/test_download_analytics.py -q
```

Expected: all tests in the file pass.

### Task 2: Add frontend query transport and route compatibility with TDD

**Files:**
- Modify: `web/src/api/client.test.ts`
- Modify: `web/src/features/admin/download-events-search.test.ts`
- Modify: `web/src/pages/admin/download-events.test.tsx`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/features/admin/download-events-search.ts`
- Modify: `web/src/features/admin/use-download-events.ts`

- [x] **Step 1: Write failing frontend contract tests**

Change the admin API list and CSV expectations to include
`userQuery=User+A`. Extend the route parser test to retain trimmed `userQuery`
and legacy `userId`. Extend the page route-initialization test to assert that a
`userQuery` value is sent to `useDownloadEvents`, and that a legacy `userId`
initializes the same combined query behavior.

- [x] **Step 2: Run the focused frontend tests and verify RED**

```powershell
cd web
corepack pnpm test -- src/api/client.test.ts src/features/admin/download-events-search.test.ts src/pages/admin/download-events.test.tsx
```

Expected: assertions fail because the frontend contracts do not contain
`userQuery`.

- [x] **Step 3: Implement the minimal frontend transport**

Add `userQuery?: string` to `DownloadEventsSearch`, `DownloadEventParams`, and
the two admin client parameter types. Serialize it as `userQuery`. In the page,
initialize one user filter from `routeSearch.userQuery ?? routeSearch.userId`,
send it as `userQuery`, reset it with the other filters, and keep URL building
through `buildApiUrl`.

- [x] **Step 4: Run the focused frontend tests and verify GREEN**

```powershell
cd web
corepack pnpm test -- src/api/client.test.ts src/features/admin/download-events-search.test.ts src/pages/admin/download-events.test.tsx
```

Expected: all selected test files pass.

### Task 3: Make the user identity readable in the UI with TDD

**Files:**
- Modify: `web/src/pages/admin/download-events.test.tsx`
- Modify: `web/src/pages/admin/download-events.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/i18n/locales/zh.json`

- [x] **Step 1: Write failing rendering and locale tests**

Assert the rendered row places `User A` before `user-a`, renders only the ID
when the display name is absent, and keeps the anonymous label when both are
absent. Assert the page uses `downloadEvents.userPlaceholder`. Extend locale
coverage so all three locale files contain the new key.

- [x] **Step 2: Run the focused UI tests and verify RED**

```powershell
cd web
corepack pnpm test -- src/pages/admin/download-events.test.tsx src/i18n/zh-tw-locale.test.ts
```

Expected: the ordering and new translation key assertions fail.

- [x] **Step 3: Implement the readable identity presentation**

Use `event.username || event.userId || anonymous` as the primary value. Render
the user ID as a secondary `font-mono` value only when both name and ID exist.
Rename the page placeholder lookup to `downloadEvents.userPlaceholder` and add:

```json
"userPlaceholder": "User name or ID..."
```

with equivalent Traditional and Simplified Chinese wording.

- [x] **Step 4: Run the focused UI tests and verify GREEN**

```powershell
cd web
corepack pnpm test -- src/pages/admin/download-events.test.tsx src/i18n/zh-tw-locale.test.ts
```

Expected: both selected test files pass.

### Task 4: Verify OpenAPI and run automated regression gates

**Files:**
- No generated-file change: the full schema remains on its existing Java-era
  baseline until the repository performs its separate full-Python generator
  cutover.

- [x] **Step 1: Verify the live FastAPI OpenAPI contract**

```powershell
curl.exe --noproxy '*' http://127.0.0.1:8080/openapi.json
```

Expected: generated operations for both admin Download Events endpoints expose
optional `userQuery`. The existing `pnpm run generate-api` points to the absent
Java-era `/v3/api-docs`; using the FastAPI schema as a replacement would rewrite
the unrelated full generated surface, so that pre-existing cutover is recorded
but not bundled into this feature.

- [x] **Step 2: Run backend and frontend gates**

```powershell
cd server-python
uv run pytest tests -q
cd ..\web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm test
corepack pnpm run build
cd ..
git diff --check
```

Expected: every command exits zero. Existing documented jsdom navigation and
Vite bundle-size notices may appear without test/build failure.

### Task 5: Verify against real services and record evidence

**Files:**
- Create: `docs/backend-python-maintenance/results/2026-08-10-download-events-human-readable-user-filter.md`

- [x] **Step 1: Start the complete local service graph**

```powershell
make dev-all
make dev-status
cd server-python
uv run python -m app.migrations upgrade
```

Expected: PostgreSQL, Redis, MinIO, scanner, FastAPI, and web report healthy,
and the Python migration command exits zero.

On the Windows verification host, where `make` was not installed, the same
service graph was started as the isolated `skillhub-download-events` Docker
Compose project plus explicit FastAPI and web processes.

- [x] **Step 2: Exercise the changed SQL against PostgreSQL**

Seed two active users sharing a readable display name, one distinct user, and
download events for each through a transaction-scoped verification script.
Call the authenticated admin JSON and CSV endpoints with a case-varied name
fragment and an ID fragment. Verify both same-name users appear, the distinct
user does not, JSON total equals returned rows, CSV contains the same identities,
and exact `userId` still returns only one account.

- [x] **Step 3: Exercise root and `/skillhub` browser paths**

Use the production web/Nginx verification path and the existing subpath
Playwright configuration. At desktop and mobile widths, open Download Events,
filter by readable name, verify the name-first/ID-second cell, export the same
filtered CSV, and confirm no request escapes the configured API base path.

```powershell
cd web
.\node_modules\.bin\playwright.CMD test -c playwright.subpath.config.ts
```

Expected: the production subpath suite exits zero and the new Download Events
scenario passes for desktop and mobile Chromium.

- [x] **Step 4: Record exact verification results**

Write the commands, pass counts, real PostgreSQL evidence, service health,
root/subpath browser outcomes, known non-failing warnings, branch, and worktree
path into the result document. Run `git status --short` and confirm only the
intended spec, plan, result, backend, frontend, translation, test, and generated
schema files changed. Do not commit, merge, push, or open a pull request.

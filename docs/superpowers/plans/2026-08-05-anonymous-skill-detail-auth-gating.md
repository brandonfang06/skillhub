# Anonymous Skill Detail Authentication Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep public Skill Detail metadata visible to anonymous visitors while preventing protected README and file-body requests until the visitor explicitly signs in.

**Architecture:** The Skill Detail page derives a protected-content permission from the existing current-user query and gates README/file-body TanStack queries with it. Expected authentication failures are represented as structured `ApiError` values and rendered inline, while public metadata and file listings keep their current backend contract. All navigation stays application-relative so the existing router applies either the root or `/skillhub` base path.

**Tech Stack:** React 19, TypeScript, TanStack Query and Router, i18next, Vitest/Testing Library, Playwright, Vite production bundle, Python/FastAPI release runtime with PostgreSQL, Redis, MinIO, scanner, and reverse proxy.

---

## File Structure

- Modify `web/src/api/client.ts`: make `fetchText` preserve HTTP status and structured server error details.
- Modify `web/src/api/client.test.ts`: prove structured and plain-text failures become `ApiError` without changing successful text behavior.
- Modify `web/src/shared/hooks/use-skill-queries.ts`: mark README and file-content queries as locally handled and retain their explicit `enabled` gates.
- Modify `web/src/shared/hooks/use-skill-queries.test.ts`: prove disabled protected queries do not fetch and query metadata skips the global handler.
- Modify `web/src/pages/skill-detail.tsx`: derive auth-aware protected-content state, render README/file-list login affordances, gate file preview, and preserve `returnTo`.
- Modify `web/src/pages/skill-detail.test.tsx`: cover anonymous, authenticated, session-expired, file-click, and action navigation behavior.
- Modify `web/src/features/skill/file-preview-dialog.tsx`: render an optional inline session-expired login action for a structured `401`.
- Modify `web/src/features/skill/file-preview-dialog.test.ts`: cover the file-preview `401` state without changing other dialog consumers.
- Modify `web/src/i18n/locales/en.json`: add English locked/session-expired content.
- Modify `web/src/i18n/locales/zh.json`: add Simplified Chinese locked/session-expired content.
- Modify `web/src/i18n/locales/zh-TW.json`: add Traditional Chinese locked/session-expired content.
- Modify `web/src/i18n/skill-detail-locale.test.ts`: assert all three locales provide the new messages.
- Modify `web/e2e/public-skill-detail-anonymous.spec.ts`: verify the real API page does not issue anonymous protected-content requests or show the generic failure.
- Modify `web/e2e/subpath-deployment.spec.ts`: verify the production bundle keeps login and `returnTo` under `/skillhub` and does not request protected content.

### Task 1: Preserve structured errors for text responses

**Files:**
- Modify: `web/src/api/client.test.ts`
- Modify: `web/src/api/client.ts:289`

- [ ] **Step 1: Write failing `fetchText` error tests**

Add cases that model the backend's real anonymous response and a non-JSON failure:

```ts
it('preserves structured error details for failed text requests', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status: 401,
    json: async () => ({ detail: 'error.auth.required', requestId: 'readme-401' }),
  }))

  await expect(fetchText('/api/web/skills/global/demo/versions/1.0.0/file?path=SKILL.md'))
    .rejects.toMatchObject({
      name: 'ApiError',
      status: 401,
      serverMessage: 'error.auth.required',
      serverMessageKey: 'error.auth.required',
      requestId: 'readme-401',
    })
})

it('preserves the status when a failed text response is not JSON', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status: 503,
    json: async () => { throw new SyntaxError('not json') },
  }))

  await expect(fetchText('/api/web/skills/global/demo/versions/1.0.0/file?path=SKILL.md'))
    .rejects.toMatchObject({ name: 'ApiError', status: 503 })
})
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.cmd run src/api/client.test.ts
```

Expected: the new assertions fail because `fetchText` currently throws a plain `Error` without `status` or server detail.

- [ ] **Step 3: Implement the minimal structured error conversion**

Change only the unsuccessful branch of `fetchText`:

```ts
if (!response.ok) {
  let errorBody: ApiErrorEnvelope<unknown> | null = null
  try {
    errorBody = await response.json() as ApiErrorEnvelope<unknown>
  } catch {
    // The HTTP status remains sufficient when an upstream returns non-JSON text.
  }
  const detail = typeof errorBody?.detail === 'string' ? errorBody.detail : undefined
  const message = errorBody?.msg || detail || `HTTP ${response.status}`
  throw new ApiError(
    message,
    response.status,
    errorBody?.msg || detail,
    errorBody?.msg || detail,
    errorBody?.requestId,
    getErrorMessageArgs(errorBody?.data),
  )
}
```

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run the command from Step 2.

Expected: all `client.test.ts` cases pass, including the existing base-path success case.

- [ ] **Step 5: Commit Task 1**

```powershell
git add web/src/api/client.ts web/src/api/client.test.ts
git commit -m "Preserve text response API errors"
```

### Task 2: Make protected content queries explicitly local and gateable

**Files:**
- Modify: `web/src/shared/hooks/use-skill-queries.test.ts`
- Modify: `web/src/shared/hooks/use-skill-queries.ts:98-121`

- [ ] **Step 1: Write failing query-behavior tests**

Import `useSkillReadme` and `useSkillFile`. Render them with a real `QueryClientProvider`, spy on `fetch`, and assert both the disabled request and query metadata:

```ts
const readmeKey = ['skills', 'global', 'demo', 'versions', '1.0.0', 'readme', 'SKILL.md']
const { result } = renderHook(
  () => useSkillReadme('global', 'demo', '1.0.0', 'SKILL.md', false),
  { wrapper },
)

expect(result.current.fetchStatus).toBe('idle')
expect(fetchMock).not.toHaveBeenCalled()
expect(queryClient.getQueryCache().find({ queryKey: readmeKey })?.meta)
  .toMatchObject({ skipGlobalErrorHandler: true })
```

Repeat for the file query key and an enabled request so the tests prove the hooks still fetch after authentication.

- [ ] **Step 2: Run the hook tests and confirm RED**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.cmd run src/shared/hooks/use-skill-queries.test.ts
```

Expected: the metadata assertions fail because these content queries do not yet opt out of the global error handler.

- [ ] **Step 3: Add local-error metadata without changing query keys**

Add the same focused metadata to both queries:

```ts
meta: {
  skipGlobalErrorHandler: true,
},
```

Keep the current `enabled && !!namespace && !!slug && !!version && !!path` checks and five-minute file-body cache.

- [ ] **Step 4: Run the hook tests and confirm GREEN**

Run the command from Step 2.

Expected: disabled queries remain idle, enabled queries fetch, and both cache entries carry local-error metadata.

- [ ] **Step 5: Commit Task 2**

```powershell
git add web/src/shared/hooks/use-skill-queries.ts web/src/shared/hooks/use-skill-queries.test.ts
git commit -m "Gate protected skill content queries"
```

### Task 3: Render anonymous and expired-session states in Skill Detail

**Files:**
- Modify: `web/src/pages/skill-detail.test.tsx`
- Modify: `web/src/pages/skill-detail.tsx:169-203`
- Modify: `web/src/pages/skill-detail.tsx:329-332`
- Modify: `web/src/pages/skill-detail.tsx:984-1025`
- Modify: `web/src/pages/skill-detail.tsx:1140-1162`
- Modify: `web/src/pages/skill-detail.tsx:1840-1850`

- [ ] **Step 1: Make the page test doubles observable**

Replace fixed content-hook mocks with `useSkillReadmeMock` and `useSkillFileMock`, include `isLoading` in `authState`, and make the FileTree double expose a clickable filename:

```tsx
FileTree: ({ onFileClick }: { onFileClick?: (node: FileTreeNode) => void }) => (
  <button
    type="button"
    onClick={() => onFileClick?.({
      id: 'SKILL.md', name: 'SKILL.md', path: 'SKILL.md', type: 'file', depth: 0,
    })}
  >
    SKILL.md
  </button>
)
```

Set the default auth state to `{ user, isLoading: false, hasRole }` and reset both content-hook mocks in `beforeEach`.

- [ ] **Step 2: Write failing anonymous page tests**

Cover public metadata, the lock card, disabled content queries, Files notice, filename login, and exact return target:

```ts
authState = { user: null, isLoading: false, hasRole: vi.fn(() => false) }
render(<SkillDetailPage />)

expect(screen.getByRole('heading', { name: 'Demo Skill' })).toBeTruthy()
expect(screen.getByText('skillDetail.readmeLoginRequiredTitle')).toBeTruthy()
expect(useSkillReadmeMock).toHaveBeenCalledWith(
  'global', 'demo-skill', '1.0.0', expect.anything(), false,
)

fireEvent.click(screen.getByText('skillDetail.signInToView'))
expect(navigateMock).toHaveBeenLastCalledWith({
  to: '/login',
  search: { returnTo: '/space/global/demo-skill' },
})

fireEvent.click(screen.getByRole('tab', { name: 'skillDetail.tabFiles' }))
expect(screen.getByText('skillDetail.filesLoginRequired')).toBeTruthy()
fireEvent.click(screen.getAllByRole('button', { name: 'SKILL.md' })[0])
expect(useSkillFileMock).toHaveBeenLastCalledWith(
  'global', 'demo-skill', '1.0.0', null, false,
)
```

Add separate coverage for `isLoading: true` so the protected area shows a neutral loading treatment rather than briefly showing the anonymous lock.

- [ ] **Step 3: Write failing authenticated and expired-session tests**

Prove an authenticated user still receives README data and file previews, then return an `ApiError` with status `401` from the README hook and assert `skillDetail.sessionExpiredTitle`, `skillDetail.signInAgain`, and no toast call.

- [ ] **Step 4: Implement auth-aware query and click gating**

Derive one page-level gate and apply it to normal and comparison README/file queries:

```ts
const { user, isLoading: isAuthLoading, hasRole } = useAuth()
const protectedContentEnabled = skillReady && !isAuthLoading && Boolean(user)

const readmeQuery = useSkillReadme(
  qns,
  qslug,
  selectedVersion,
  documentationPath,
  protectedContentEnabled,
)
```

Prevent preview state from opening anonymously:

```ts
const handleFileClick = (node: FileTreeNode) => {
  if (isAuthLoading) return
  if (!user) {
    requireLogin()
    return
  }
  setPreviewNode(node)
  setPreviewDialogOpen(true)
}
```

In the README branch, order states as auth loading, anonymous lock, authenticated `401` session-expired card, success, other failure, and no documentation. Reuse `Card`, `Button`, and the existing `Lock` icon; do not add a generic auth component.

Render the Files notice only after auth has resolved anonymous, above both the main Files tab tree and the existing sidebar tree. Pass `requireLogin` to the preview dialog for the session-expired case.

- [ ] **Step 5: Run page tests and confirm GREEN**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.cmd run src/pages/skill-detail.test.tsx
```

Expected: anonymous, authenticated, lifecycle, link-resolution, and error-state tests all pass.

- [ ] **Step 6: Commit Task 3**

```powershell
git add web/src/pages/skill-detail.tsx web/src/pages/skill-detail.test.tsx
git commit -m "Guide anonymous skill detail users to login"
```

### Task 4: Handle session expiry inside file preview and localize all states

**Files:**
- Modify: `web/src/features/skill/file-preview-dialog.test.ts`
- Modify: `web/src/features/skill/file-preview-dialog.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/i18n/skill-detail-locale.test.ts`

- [ ] **Step 1: Write a failing file-preview `401` test**

Render the dialog with `new ApiError('error.auth.required', 401)`, pass `onRequireLogin`, and assert the session-expired title plus button. Click the button and assert the callback runs. Keep the existing generic error test for non-`401` errors.

- [ ] **Step 2: Write failing locale-contract tests**

Assert the following keys are non-empty in `en`, `zh`, and `zh-TW` and that Traditional Chinese uses the approved `登入查看` label:

```ts
const locales = [en, zh, zhTW]
for (const locale of locales) {
  expect(locale.skillDetail.readmeLoginRequiredTitle).toBeTruthy()
  expect(locale.skillDetail.readmeLoginRequiredDescription).toBeTruthy()
  expect(locale.skillDetail.signInToView).toBeTruthy()
  expect(locale.skillDetail.filesLoginRequired).toBeTruthy()
  expect(locale.skillDetail.sessionExpiredTitle).toBeTruthy()
  expect(locale.skillDetail.sessionExpiredDescription).toBeTruthy()
  expect(locale.skillDetail.signInAgain).toBeTruthy()
}
expect(zhTW.skillDetail.signInToView).toBe('登入查看')
```

- [ ] **Step 3: Run focused tests and confirm RED**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.cmd run src/features/skill/file-preview-dialog.test.ts src/i18n/skill-detail-locale.test.ts
```

Expected: the new optional login UI and locale keys are missing.

- [ ] **Step 4: Add the optional file-preview login state**

Add `onRequireLogin?: () => void` to `FilePreviewDialogProps`. When `error` is an `ApiError` with status `401` and the callback exists, render the localized session-expired title, description, and `Sign in again` button. Leave review and dashboard callers unchanged because the prop is optional.

- [ ] **Step 5: Add all three locale translations**

Use these exact semantic messages:

```text
English: Sign in to view the README / Sign in to view / Sign in to preview file contents.
Simplified Chinese: 登录后查看 README / 登录查看 / 登录后可预览文件内容。
Traditional Chinese: 登入後查看 README / 登入查看 / 登入後可預覽檔案內容。
```

Also add distinct session-expired title, description, and re-login action in each locale. Do not alter unrelated existing translations.

- [ ] **Step 6: Run focused tests and confirm GREEN**

Run the command from Step 3 plus `src/pages/skill-detail.test.tsx`.

Expected: all affected component and locale tests pass.

- [ ] **Step 7: Commit Task 4**

```powershell
git add web/src/features/skill/file-preview-dialog.tsx web/src/features/skill/file-preview-dialog.test.ts web/src/i18n/locales/en.json web/src/i18n/locales/zh.json web/src/i18n/locales/zh-TW.json web/src/i18n/skill-detail-locale.test.ts
git commit -m "Localize protected skill content states"
```

### Task 5: Prove anonymous behavior in real and subpath browser flows

**Files:**
- Modify: `web/e2e/public-skill-detail-anonymous.spec.ts`
- Modify: `web/e2e/subpath-deployment.spec.ts`

- [ ] **Step 1: Extend the real-API anonymous test**

Collect only protected content responses, excluding the expected anonymous `/api/v1/auth/me` probe:

```ts
const protectedContentResponses: number[] = []
page.on('response', (response) => {
  const url = new URL(response.url())
  if (/\/versions\/[^/]+\/file$/.test(url.pathname)) {
    protectedContentResponses.push(response.status())
  }
})
```

After opening the seeded public skill, assert the public heading, README lock card, Files tab and filename list, no `Operation failed` toast, and `protectedContentResponses` is empty. Click `Sign in to view` and assert `/login?returnTo=...` contains the application-relative Skill Detail path.

- [ ] **Step 2: Extend the subpath mock observer and add a failing production-bundle test**

Add `protectedContentPaths: string[]` to `ObservedRequests`, record file-body paths in the router, and add an anonymous test:

```ts
await page.goto(`${basePath}/space/global/subpath-skill`)
await expect(page.getByRole('heading', { name: 'Subpath Skill', exact: true }).first()).toBeVisible()
await expect(page.getByText('Sign in to view the README')).toBeVisible()
expect(observed.protectedContentPaths).toEqual([])

await page.getByRole('button', { name: 'Sign in to view' }).click()
await expect(page).toHaveURL(
  /\/skillhub\/login\?returnTo=%2Fspace%2Fglobal%2Fsubpath-skill$/,
)
expect(observed.apiRootEscapes).toEqual([])
```

- [ ] **Step 3: Run production build and mocked subpath E2E**

Run:

```powershell
cd web
.\node_modules\.bin\tsc.cmd -b
.\node_modules\.bin\vite.cmd build
.\node_modules\.bin\playwright.cmd test -c playwright.subpath.config.ts
```

Expected: build succeeds; all desktop and mobile subpath scenarios pass; the new anonymous scenario makes no protected-content request and retains `/skillhub`.

- [ ] **Step 4: Run the real-API E2E against the complete local topology**

Start or rebuild PostgreSQL, Redis, MinIO, scanner, Python backend, web, and the subpath proxy using the repository's current release-compose workflow. Confirm every service is healthy before Playwright. Run the focused real-API spec with the repository's required E2E credentials:

```powershell
cd web
.\node_modules\.bin\playwright.cmd test e2e/public-skill-detail-anonymous.spec.ts
```

Expected: the seeded public skill remains visible anonymously, no protected README/file-body request occurs, no generic failure appears, and login preserves the Skill Detail target.

- [ ] **Step 5: Commit Task 5**

```powershell
git add web/e2e/public-skill-detail-anonymous.spec.ts web/e2e/subpath-deployment.spec.ts
git commit -m "Cover anonymous skill detail browser flows"
```

### Task 6: Complete regression, review, and merge-readiness verification

**Files:**
- Verify only; update this plan's checkboxes with results if useful.

- [ ] **Step 1: Run focused tests together**

```powershell
cd web
.\node_modules\.bin\vitest.cmd run src/api/client.test.ts src/shared/hooks/use-skill-queries.test.ts src/pages/skill-detail.test.tsx src/features/skill/file-preview-dialog.test.ts src/i18n/skill-detail-locale.test.ts
```

Expected: all focused tests pass.

- [ ] **Step 2: Run complete frontend gates**

```powershell
cd web
.\node_modules\.bin\vitest.cmd run
.\node_modules\.bin\tsc.cmd --noEmit
.\node_modules\.bin\eslint.cmd . --ext ts,tsx --report-unused-disable-directives --max-warnings 0
.\node_modules\.bin\tsc.cmd -b
.\node_modules\.bin\vite.cmd build
```

Expected: full tests, typecheck, lint, and production build all pass.

- [ ] **Step 3: Repeat live browser acceptance through `/skillhub`**

With the complete PostgreSQL-backed topology still healthy, verify anonymous README, Files, filename click, representative social/report/playground actions, login navigation, authenticated README/file preview, direct reload, and back/forward behavior. Inspect browser network and console; distinguish the expected anonymous `/auth/me` probe from forbidden feature-generated content requests.

- [ ] **Step 4: Review the complete branch diff**

Compare with `dev`, confirm the implementation matches the spec, and inspect shared-helper callers for regressions:

```powershell
git diff --check dev...HEAD
git diff --stat dev...HEAD
git status --short
```

Expected: no whitespace errors, no generated/schema/backend/deployment changes, and no unrelated files.

- [ ] **Step 5: Stop before merge**

Report the branch, commits, exact automated results, live service health, browser observations, and any residual risks. Do not merge, push, or modify `dev` until the user explicitly accepts the completed feature.

## Execution Record

**Completed:** 2026-08-05

**Branch:** `codex/anonymous-skill-detail-auth-gating`

**Verified implementation commit:** `ce2326d1c0131e0f17c12356bb5a7b891a65dec7`

- Full Vitest regression: 203 test files, 798 tests passed.
- TypeScript `tsc --noEmit`: passed.
- ESLint with zero warnings allowed: passed.
- Fresh TypeScript/Vite production build: passed.
- Production subpath Playwright suite: 18/18 desktop and mobile cases passed.
- Real-API browser flow on the final production image: 1/1 passed at both
  root path and `/skillhub`.
- The real flow created and approved a PostgreSQL-backed public skill, proved
  anonymous README/file requests and Star mutations were not sent, followed
  filename and README login paths, returned to the exact Skill Detail route,
  rendered authenticated README and file content, and survived reload.
- PostgreSQL accepted connections; Redis returned `PONG`; MinIO, scanner,
  Python backend, final root web, final `/skillhub` web, and both verification
  proxies were healthy.
- Standards and spec reviews both passed after the shared `buildReturnTo`
  correction and expanded browser coverage.
- `git diff --check dev...HEAD` passed and the feature worktree was clean.

No backend, schema, generated API, deployment manifest, or environment-variable
contract changed. The branch was intentionally kept unmerged and unpushed for
user acceptance.

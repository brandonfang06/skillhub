# UI Runtime Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent visibility controls from overflowing their sidebar and recover once from stale Vite route chunks after deployment.

**Architecture:** Keep layout repair local to the skill detail page. Add a testable preload-error recovery helper under the app layer and install it from bootstrap before any lazy route import. Preserve immutable hashed assets while requiring SPA entry responses to revalidate.

**Tech Stack:** React 19, TypeScript, Vite 6, TanStack Router, Tailwind CSS, Vitest, Playwright, Nginx

---

### Task 1: Persist the approved behavior

**Files:**
- Create: `docs/superpowers/specs/2026-07-28-ui-runtime-resilience-design.md`
- Create: `docs/superpowers/plans/2026-07-28-ui-runtime-resilience.md`

- [x] **Step 1: Record the confirmed root causes**

Document the fixed-width sidebar/container-breakpoint mismatch and the old-tab-to-missing-hash
deployment sequence.

- [x] **Step 2: Record recovery and cache invariants**

Specify one guarded reload per preload fingerprint, no reload loop, immutable hashed assets,
and revalidated SPA HTML.

### Task 2: Add stale chunk regression coverage

**Files:**
- Create: `web/src/app/preload-error-recovery.test.ts`
- Create: `web/src/app/preload-error-recovery.ts`
- Modify: `web/src/bootstrap.ts`

- [ ] **Step 1: Write failing recovery tests**

Cover these cases with injected storage, clock, and reload dependencies:

```ts
expect(recoverFromPreloadError(firstEvent, runtime)).toBe(true)
expect(firstEvent.defaultPrevented).toBe(true)
expect(runtime.reload).toHaveBeenCalledOnce()

expect(recoverFromPreloadError(repeatedEvent, runtime)).toBe(false)
expect(repeatedEvent.defaultPrevented).toBe(false)
expect(runtime.reload).toHaveBeenCalledOnce()
```

Also assert storage failures leave the event unhandled and do not reload.

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
cd web
corepack pnpm exec vitest run src/app/preload-error-recovery.test.ts
```

Expected: fail because `preload-error-recovery.ts` does not exist.

- [ ] **Step 3: Implement the recovery helper**

Create a typed helper with a 60-second repeat guard:

```ts
export function recoverFromPreloadError(
  event: VitePreloadErrorEvent,
  runtime: PreloadRecoveryRuntime,
): boolean
```

Persist `{ fingerprint, attemptedAt }` in session storage before calling
`event.preventDefault()` and `runtime.reload()`.

- [ ] **Step 4: Install recovery before the main import**

Call `installPreloadErrorRecovery()` from `bootstrap.ts` before the asynchronous runtime-config
bootstrap imports `main.tsx`.

- [ ] **Step 5: Run the focused test and confirm GREEN**

Run:

```powershell
cd web
corepack pnpm exec vitest run src/app/preload-error-recovery.test.ts
```

Expected: all recovery tests pass.

### Task 3: Lock the deployed cache contract

**Files:**
- Create: `web/src/app/web-cache-policy.test.ts`
- Modify: `web/nginx.conf.template`

- [ ] **Step 1: Write a failing Nginx policy test**

Read `nginx.conf.template` and assert:

```ts
expect(spaLocation).toContain('Cache-Control "no-cache, must-revalidate"')
expect(assetLocation).toContain('Cache-Control "public, immutable"')
expect(runtimeConfigLocation).toContain('Cache-Control "no-store"')
```

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
cd web
corepack pnpm exec vitest run src/app/web-cache-policy.test.ts
```

Expected: fail because the SPA location has no explicit cache policy.

- [ ] **Step 3: Add the SPA revalidation header**

Add this header to `location /` without changing the more-specific asset or runtime-config
locations:

```nginx
add_header Cache-Control "no-cache, must-revalidate";
```

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run the Task 3 test again and expect all assertions to pass.

### Task 4: Make visibility controls container-safe

**Files:**
- Modify: `web/src/pages/skill-detail.tsx`
- Modify: `web/src/pages/skill-detail.test.tsx`
- Modify: `web/e2e/skill-lifecycle-visibility.spec.ts`

- [ ] **Step 1: Add failing layout assertions**

Give the controls a stable test id and assert the unit-rendered control group uses one column.
Extend the authenticated viewport E2E to compare the panel, select, and button bounding boxes:

```ts
expect(selectBox.x).toBeGreaterThanOrEqual(panelBox.x)
expect(selectBox.x + selectBox.width).toBeLessThanOrEqual(panelBox.x + panelBox.width)
expect(buttonBox.x + buttonBox.width).toBeLessThanOrEqual(panelBox.x + panelBox.width)
```

- [ ] **Step 2: Run the unit test and confirm RED**

Run:

```powershell
cd web
corepack pnpm exec vitest run src/pages/skill-detail.test.tsx
```

Expected: fail because the current group still uses `sm:flex-row`.

- [ ] **Step 3: Implement the one-column layout**

Use a constrained single-column grid, a `min-w-0 max-w-full` select trigger, and a full-width
button whose localized text may wrap.

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run the Task 4 unit test and expect all assertions to pass.

### Task 5: Verify the complete frontend

**Files:**
- Verify all modified frontend and deployment files

- [ ] **Step 1: Run focused regression tests**

```powershell
cd web
corepack pnpm exec vitest run src/app/preload-error-recovery.test.ts src/app/web-cache-policy.test.ts src/pages/skill-detail.test.tsx
```

- [ ] **Step 2: Run full frontend gates**

```powershell
corepack pnpm exec vitest run --maxWorkers=4
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run build
```

- [ ] **Step 3: Run authenticated viewport verification**

Start the local services using the repository workflow, then run the lifecycle visibility
Playwright scenario at desktop and mobile widths. Confirm no control bounding box exceeds its
panel and no horizontal document overflow appears.

- [ ] **Step 4: Review the final diff**

```powershell
git diff --check
git status --short
git diff --stat
```

Confirm only the approved specification, plan, recovery, cache, layout, and regression files
changed. Do not commit, merge, or push without explicit user authorization.

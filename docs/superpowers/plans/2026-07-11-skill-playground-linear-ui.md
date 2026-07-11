# Skill Playground Linear UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing prompt-only Playground into a compact, chat-first Linear-adapted workspace without changing backend or sidecar contracts.

**Architecture:** Keep route orchestration in `skill-playground.tsx`, extract the read-only context browser into a Playground feature component, and use Radix Dialog only inside that feature for the responsive drawer. Preserve `usePlayground` network/session behavior while deriving a local completion marker from existing events; derive the install prompt from completed local assistant messages and reuse the existing install command builder.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Radix Dialog, lucide-react, Vitest, Testing Library, Playwright

---

### Task 1: Lock The Updated Design Boundary

**Files:**
- Modify: `docs/superpowers/specs/2026-07-11-skill-playground-linear-ui-design.md`
- Create: `docs/superpowers/plans/2026-07-11-skill-playground-linear-ui.md`

- [x] Remove the lavender/indigo contradiction from the approved spec.
- [x] Record scoped Radix Dialog, transcript-derived install CTA, `100dvh`, safe-area, and no-global-theme constraints.
- [x] Run a placeholder and contradiction scan over the spec and plan.

### Task 2: Responsive Read-Only Context Browser

**Files:**
- Create: `web/src/features/playground/playground-context.tsx`
- Create: `web/src/features/playground/playground-context.test.tsx`
- Modify: `web/package.json`
- Modify: `web/pnpm-lock.yaml`

- [x] Add `@radix-ui/react-dialog` with pnpm.
- [x] Write failing tests proving file selection, path tooltip/truncation, and dialog trigger/content semantics.
- [x] Run `corepack pnpm test -- src/features/playground/playground-context.test.tsx` and confirm failures describe missing behavior.
- [x] Implement one shared context browser body rendered as a desktop panel and a Radix right-side drawer.
- [x] Re-run the targeted context tests and confirm they pass.

### Task 3: Workspace Page And Responsive Hierarchy

**Files:**
- Modify: `web/src/pages/skill-playground.tsx`
- Modify: `web/src/pages/skill-playground.test.tsx`

- [x] Add failing page tests for the scoped dark workspace, compact metadata, chat-first DOM order, and context toggle wiring.
- [x] Run `corepack pnpm test -- src/pages/skill-playground.test.tsx` and confirm the new assertions fail.
- [x] Replace the flat grid with a `100dvh`-bounded workspace, desktop context sibling, and chat-first mobile order.
- [x] Keep all dark surface values local to the Playground root and avoid global token changes.
- [x] Re-run the targeted page tests and confirm they pass.

### Task 4: Transcript, Composer, States, And Install CTA

**Files:**
- Modify: `web/src/features/playground/playground-chat.tsx`
- Modify: `web/src/features/playground/playground-chat.test.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/i18n/locales/zh.json`

- [x] Add failing tests for completed-response install CTA, no CTA while streaming, reload action for expired state, and disabled composer states.
- [x] Run `corepack pnpm test -- src/features/playground/playground-chat.test.tsx` and confirm failures describe the missing UI.
- [x] Implement neutral assistant messages, indigo user messages, anchored composer, compact reset, reload action, and transcript-derived install CTA.
- [x] Reuse `buildSkillhubInstallCommand`, `getBaseUrl`, and the existing clipboard hook; add no API calls.
- [x] Add English, Traditional Chinese, and Simplified Chinese strings.
- [x] Re-run the targeted chat and locale tests and confirm they pass.

### Task 5: Automated And Isolation Verification

**Files:**
- Modify only test files if verification reveals a Playground-scoped defect.

- [x] Run `corepack pnpm test`.
- [x] Run `corepack pnpm run typecheck`.
- [x] Run `corepack pnpm run lint`.
- [x] Run `corepack pnpm run build`.
- [x] Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-playground-isolation.ps1`.
- [x] Run `git diff --check` and confirm no backend, sidecar, global theme, or shared shell file changed.

### Task 6: Browser Verification

**Files:**
- Modify only Playground-scoped files if visual verification reveals a defect.

- [x] Verify empty and populated desktop layouts at 1440x900.
- [x] Verify desktop/tablet split at 1024x768.
- [x] Verify context drawer behavior at 800x900.
- [x] Verify chat-first mobile layout, drawer, composer, overflow, and touch targets at 390x844.
- [x] Verify connecting, streaming, recoverable error, unavailable, and expired states without overlap.
- [x] Confirm the skill detail page and one unrelated route remain visually unchanged.

### Task 7: Delivery

- [x] Review the final diff against the approved spec.
- [x] Commit the isolated UI change on `codex/skill-playground`.
- [x] Keep the local SkillHub, sidecar, and model services available for user testing.

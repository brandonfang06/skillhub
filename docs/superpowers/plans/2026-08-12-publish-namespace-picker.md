# Publish Namespace Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the publish page's plain namespace Select with a searchable, scrollable, keyboard-accessible picker that remains compatible with existing publish behavior.

**Architecture:** Add one publish-specific component backed by the existing Radix dropdown-menu wrapper and keep `PublishPage` as the owner of the selected slug. Filtering is local and pure; no API or shared Select changes are required.

**Tech Stack:** React 19, TypeScript, Radix Dropdown Menu, Tailwind CSS, i18next, Vitest, Testing Library, Playwright/browser viewport verification.

---

### Task 1: Search And Selection Contract

**Files:**
- Create: `web/src/features/publish/namespace-picker.test.tsx`
- Create: `web/src/features/publish/namespace-picker.tsx`

- [ ] **Step 1: Write failing tests for filtering and selection**

Add tests that construct 125 namespaces and assert that filtering matches
`displayName` and `slug` case-insensitively, excludes unrelated values, reports
an empty result, invokes `onValueChange(slug)` on selection, and invokes
`onValueChange('')` when cleared.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run src/features/publish/namespace-picker.test.tsx
```

Expected: FAIL because `namespace-picker.tsx` does not exist.

- [ ] **Step 3: Implement the minimal picker**

Implement and export:

```ts
export interface NamespacePickerProps {
  namespaces: ManagedNamespace[]
  value: string
  onValueChange: (value: string) => void
  labelId: string
}

export function filterNamespaces(
  namespaces: ManagedNamespace[],
  query: string,
): ManagedNamespace[]
```

Use the shared DropdownMenu wrappers, Select trigger class, controlled open and
query state, scrollable results, selected check marker, and localized labels.

- [ ] **Step 4: Verify focused tests pass**

Run the Task 1 command and expect all namespace picker tests to pass.

### Task 2: Publish Page Integration

**Files:**
- Modify: `web/src/pages/dashboard/publish.tsx`
- Modify: `web/src/pages/dashboard/publish.test.ts`

- [ ] **Step 1: Update publish tests first**

Mock `NamespacePicker`, capture its `value`, and verify route prefill still sends
`team-ai`, missing search params still send an empty slug, and picker changes
continue to control whether Confirm Publish is enabled.

- [ ] **Step 2: Verify the integration test fails**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run src/pages/dashboard/publish.test.ts
```

Expected: FAIL because PublishPage still imports and renders the plain Select.

- [ ] **Step 3: Replace only the namespace Select**

Render `NamespacePicker` with `namespaces ?? []`, `namespaceSlug`,
`setNamespaceSlug`, and the namespace label id. Keep the visibility Select,
publish mutation, prefill effect, and required-field behavior unchanged.

- [ ] **Step 4: Verify picker and publish tests pass together**

Run both focused test files and expect all tests to pass.

### Task 3: Localized User Feedback

**Files:**
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/i18n/locales/zh.json`

- [ ] **Step 1: Add translation assertions**

Extend the picker tests to require localized keys for search placeholder, search
label, clear selection, and no matching namespace.

- [ ] **Step 2: Add all three locale values**

Add these keys under `publish`:

```json
{
  "namespaceSearchLabel": "Search namespaces",
  "namespaceSearchPlaceholder": "Search namespace name or slug...",
  "clearNamespace": "Clear namespace selection",
  "noMatchingNamespace": "No matching namespace"
}
```

Use equivalent Simplified and Traditional Chinese text in their locale files.

- [ ] **Step 3: Run focused tests and JSON/type checks**

Run the picker and publish tests, then TypeScript typecheck.

### Task 4: Regression And Browser Verification

**Files:**
- Modify if evidence requires: files from Tasks 1-3 only
- Record: `docs/backend-python-maintenance/results/2026-08-12-publish-namespace-picker.md`

- [ ] **Step 1: Run full frontend gates**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD . --ext ts,tsx --report-unused-disable-directives --max-warnings 0
.\node_modules\.bin\tsc.CMD -b
.\node_modules\.bin\vite.CMD build
```

Expected: all commands exit 0 and `pnpm-lock.yaml` remains unchanged.

- [ ] **Step 2: Run authenticated browser scenarios**

Verify desktop and mobile publish views with at least 125 namespaces: open the
picker, scroll to later entries, filter by display name, filter by slug, select,
clear, observe empty results, and confirm no horizontal overflow or browser
console errors.

- [ ] **Step 3: Review side effects**

Review the final diff for shared-component changes, payload changes, route
prefill regression, selection clearing, focus traps, mobile overflow, and
rendering cost. Fix any reproduced issue and rerun the affected gates.

- [ ] **Step 4: Stop before integration**

Do not commit, merge, or push. Report the verified branch and exact results, then
wait for explicit user authorization to integrate with `dev`.

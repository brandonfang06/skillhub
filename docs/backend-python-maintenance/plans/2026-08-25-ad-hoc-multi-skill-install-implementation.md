# Ad Hoc Multi-Skill Install Implementation Plan

## Goal And Baseline

Implement the approved design in
`2026-08-25-ad-hoc-multi-skill-install-design.md` as a frontend-owned,
authenticated, tab-scoped workflow. Reuse the released public
`@astron-team/skillhub@latest` CLI unchanged and preserve the existing Python
backend, PostgreSQL download analytics, `/skillhub` sub-path, and single-skill
install UI.

No commit or push is part of this plan.

## 2026-08-26 Follow-up

The approved design amendment changes the frontend implementation baseline:

- replace persisted Agent arrays and checkbox UI with one supported Agent ID;
- migrate an existing tab state by retaining the first supported Agent in CLI
  detector order;
- always append `--force` and remove the Force state/control;
- move the Search continuation row above results;
- order the Install page as targets, commands, and a collapsed three-row
  selected-Skills disclosure; and
- remove terminal-identity guidance.

Verification must execute the generated single-Agent command with the published
npm 0.1.9 bundle. Repository-only CLI tests are supplementary and cannot prove
the public artifact contract.

## Public Test Seams

1. Pure command renderer: coordinates plus shared target options produce exact
   cross-shell CLI lines.
2. Install-selection store: authenticated owner, versioned session persistence,
   limit, deduplication, sort, options, clear, and identity reset.
3. Search workflow: authenticated entry, card selection, limit feedback,
   persistent tray, clear, and navigation.
4. Install page: empty state, removal, Scope, Agent multiselect, force warning,
   identity guidance, and copy actions.
5. Runtime integration: public npm CLI downloads through the real FastAPI route
   and writes existing per-skill events to real PostgreSQL.

## Phase 1 - State And Search Selection

- Add a feature-owned Zustand store under `web/src/features/install-selection/`.
- Persist only versioned workflow state to `sessionStorage`; bind it to the
  authenticated string `userId` and reset after logout or identity change.
- Cap unique canonical `namespace/slug` entries at 20.
- Extend `SkillCard` through opt-in selection props without changing other
  consumers.
- Add authenticated multi-select entry and a persistent bottom selection tray
  to `/search`.

Success criteria:

- Store and interaction tests go red before implementation and then pass.
- Ordinary cards remain keyboard links outside selection mode.
- Search/filter/sort/page changes do not clear selected items.
- At 20 entries, unselected cards are disabled with a visible reason while
  removal remains possible.

## Phase 2 - Install Page And Command Renderer

- Register authenticated logical route `/install` and add it to the centered
  app layout.
- Extend the existing pure SkillHub command builder with required Scope,
  repeated supported Agents, and optional `--force` while preserving the
  existing single-skill call signature.
- Render a stable unique namespace/slug-sorted list and one independent command
  per skill.
- Provide Scope default `user`, no default Agent, the exact 14 released
  explicit Agent profiles, no Generic, and reinstall-latest default off.
- Disable copy until at least one Agent is selected. Provide copy-all and
  per-command actions, plus CLI identity guidance.

Success criteria:

- Literal command tests prove no `--version`, token, Generic, custom directory,
  or shell wrapper is emitted.
- `/skillhub` registry paths remain intact.
- Empty state, removal/clear, warnings, and target validation pass component
  tests.
- Desktop and 390 px layouts have no hidden controls or horizontal overflow.

## Phase 3 - Quality And Documentation

- Add English, Simplified Chinese, and Traditional Chinese resources plus
  locale parity coverage.
- Verify native labels, checkbox states, disabled explanations, polite live
  count, focus recovery, and keyboard interaction.
- Update user/operator documentation only where the visible workflow or CLI
  identity prerequisite needs explanation; do not describe Generic as a batch
  target.

Required commands:

```powershell
cd web
pnpm test -- <focused test files>
pnpm run test
pnpm run typecheck
pnpm run lint
pnpm run build
pnpm run test:e2e:subpath
```

## Phase 4 - Real-Service Integration

Start PostgreSQL, Redis, MinIO, scanner, FastAPI backend, and Web using the
repository development workflow. Apply Python-owned migrations and verify all
health endpoints before browser acceptance.

Use a real authenticated browser session to verify login return, cross-page
selection, refresh persistence, 20-item feedback, `/install`, Agent choices,
force warning, copy-all/per-line copy, logout reset, and `/skillhub` routing.

Use the released npm CLI and real backend data to prove:

- two successful selected-skill downloads create two PostgreSQL rows with
  `source = 'cli'` for the authenticated CLI bearer;
- an unauthenticated download creates no event;
- a pre-download failure creates no event; and
- a partial command run leaves only the successful download event.

Record exact commands, health results, event identifiers/counts, and cleanup.
Mocks remain supplementary and cannot replace this phase.

## Non-Goals

- No Collection resource or curator/discovery pages.
- No backend endpoint, schema, or migration for the ephemeral list.
- No CLI modification, build, fork, release, or npm publication.
- No batch Generic, `--dir`, pinned skill version, shell-specific wrapper,
  browser credential handoff, or Web/CLI identity equality enforcement.
- No synthetic copy/install analytics and no claim that copied text was run.

# Global Namespace Auto-Join And External Source Link

## Goal

1. Stop adding every newly registered user to the built-in `global` namespace by
   default. Operators may restore the legacy behavior explicitly.
2. Remove the external GitHub source link from Skill detail because organization
   development environments cannot access the public internet.

## Decisions

- `SKILLHUB_GLOBAL_NAMESPACE_AUTO_JOIN_ENABLED` controls automatic membership
  for newly created local and OAuth accounts.
- The setting defaults to `false`. Only the normal true values accepted by the
  existing boolean parser (`1`, `true`, `yes`, `on`) enable it.
- This setting does not delete or hide the `global` namespace, remove existing
  members, change public skill reads, or change promotion authorization.
- Enabling the setting restores the previous `MEMBER` insertion behavior for
  new local and OAuth accounts.
- No backfill or removal job is introduced. Existing namespace membership is
  operator-owned data and remains unchanged.
- Skill detail continues to show source ref and repository-relative path but no
  longer renders an external repository link.
- The pipeline contract, database schema, API provenance object, commit SHA, and
  content fingerprint remain unchanged. This avoids an API breaking change and
  keeps immutable import, scan, and review evidence available to internal tools.

## Verification Seams

- Configuration: missing env is false; explicit true is true.
- Local registration: default creates no global membership; opt-in creates one.
- OAuth account creation: default creates no global membership; opt-in creates
  one. Existing account login does not mutate membership.
- Real PostgreSQL: only the opt-in OAuth account receives a `global` membership
  row.
- Skill detail UI: source ref and path remain visible; no anchor or external URL
  is rendered.
- Deployment: Compose, Kustomize base/plain manifests, env example, and operator
  documentation expose the backend setting with a false default.

## Security And Side Effects

- Confidentiality: default-off membership reduces unnecessary namespace
  association. It does not make global public skills private.
- Integrity: hiding the link does not replace or weaken the commit SHA and
  fingerprint used by import validation and review.
- Availability: registration succeeds whether auto-join is disabled or the
  global namespace is absent. Internal users no longer receive a dead external
  navigation target.
- Rollback: unset or set the env to `false` to stop future auto-joins; set it to
  `true` to restore legacy behavior. Changing it never rewrites existing rows.
  The UI link can be restored later without a migration because `browseUrl`
  remains in the API contract.

## Verification Results

- Backend focused tests: 160 passed, 1 skipped.
- Backend full suite: 1760 passed, 54 skipped.
- Real PostgreSQL 16 integration: migrations reached
  `skillhub_flyway_v45_baseline`; the default account had no `global`
  membership and the opt-in account had exactly one.
- Frontend: 1025 Vitest tests passed; typecheck, ESLint, and the production Vite
  build passed.
- Deployment rendering: Kustomize base and release Compose config both expose
  the setting with a `false` default.
- Browser E2E: desktop and mobile Chromium `/skillhub` Skill detail scenarios
  passed, including no external source anchor, no horizontal overflow,
  authenticated download, and logout. The earlier desktop failure was confirmed
  as local C drive/pagefile exhaustion; it passed after disk and Docker cleanup.

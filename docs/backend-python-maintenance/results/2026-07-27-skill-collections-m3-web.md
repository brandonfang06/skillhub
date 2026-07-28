# Skill Collections M3 Web Result

Date: 2026-07-27
Milestone: M3 only
Status: complete; stopped before M4

## Delivered Contract

- Added a separate, default-off Collections tab to the namespace page without
  changing the existing skill search request or empty state.
- Added public collection detail at
  `/space/{namespace}/collections/{collection}`.
- Added authenticated curator routes at
  `/dashboard/namespaces/{namespace}/collections` and
  `/dashboard/namespaces/{namespace}/collections/{collection}`.
- Added typed collection HTTP functions and TanStack Query hooks for list,
  detail, create, draft, publish, and status workflows.
- Kept backend `canCurate` authoritative and did not add a collection owner.
- Added ordered exact-version member editing, advisory newer-version notices,
  member diff, and advisory collection semver suggestions.
- Draft save forwards the current revision through `If-Match`; create and
  publish generate idempotency keys.
- Added an exact two-registry install command. It renders only when Nexus
  registry, internal package, immutable non-`latest` CLI version, SkillHub URL,
  collection coordinate, and published collection version are all valid.
- Reused existing SkillHub cards, buttons, inputs, tabs, borders, focus rings,
  and color tokens.
- Added matching English, Simplified Chinese, and Traditional Chinese locale
  keys.
- GitLab import remains disabled and unimplemented in M3.

## TDD Evidence

Observed red states included missing runtime normalization, query keys, API and
hook modules, diff and install builders, card and member editor, pages, and
routes. The browser gate initially rendered a blank page because an overly
broad Playwright glob intercepted `/src/api/client.ts` as though it were a
backend request. The mock was narrowed to URL pathnames beginning with
`/api/`, after which all four browser contracts passed.

Focused collection coverage:

```text
corepack pnpm run test \
  src/api/client.test.ts \
  src/shared/hooks/query-keys.test.ts \
  src/features/collection \
  src/pages/namespace.test.tsx \
  src/pages/collection-detail.test.tsx \
  src/pages/dashboard/namespace-collections.test.tsx \
  src/pages/dashboard/collection-maintenance.test.tsx \
  src/app/router.test.ts \
  src/i18n/collection-locale.test.ts
```

Result: `14 passed` files, `83 passed` tests.

Browser contracts:

```text
corepack pnpm run test:e2e \
  e2e/collection-catalog.spec.ts \
  e2e/collection-install-command.spec.ts \
  e2e/collection-maintenance.spec.ts \
  e2e/collection-role-access.spec.ts
```

Result: `4 passed`.

## Full Verification

Frontend:

- `corepack pnpm run typecheck`: exit `0`.
- `corepack pnpm run lint`: exit `0`.
- `corepack pnpm run test`: `204 passed` files, `733 passed` tests.
- `corepack pnpm run build`: exit `0`; existing runtime-config URL and large
  chunk warnings remain.

Python backend:

- `.venv\Scripts\python.exe -m pytest tests -q`: `1006 passed`, one existing
  Starlette/httpx deprecation warning, `178.59s`.

CLI:

- `bun run lint`: exit `0`.
- `bun run typecheck`: exit `0`.
- `bun test`: `410 pass`, `6 skip`, `0 fail`, `1116` expectations.
- `bun run build`: exit `0`.
- `node dist/index.js version`: `SkillHub CLI 0.1.9`.

Operator gates:

- `kubectl kustomize deploy\k8s\base`: exit `0`.
- `docker compose --env-file .env.release.example -f compose.release.yml
  config --quiet`: exit `0`, with the existing sandbox warning while reading
  the user Docker config.
- `git diff --check`: no whitespace error; Windows LF-to-CRLF notices only.

## Stop Condition And Non-Goals

M3 did not add GitLab clients, import schema, import APIs, import UI, or scanner
changes. It did not publish a CLI package, write to Nexus, enable feature flags,
deploy, stage, commit, push, or open a pull request.

# Ad Hoc Multi-Skill Install Verification

Date: 2026-08-25

## Scope

- Added an authenticated multi-select mode to `/search` with a 20-Skill limit,
  tab-scoped persistence, deterministic canonical deduplication, and explicit
  clear/focus behavior.
- Added protected `/install` configuration for user/project scope, the 14
  released explicit Agent targets, optional `--force`, CLI identity guidance,
  and per-command/copy-all output.
- Kept the public `@astron-team/skillhub@latest` CLI unchanged. No backend API,
  schema, migration, CLI build, CLI fork, or npm publication was added.
- Preserved both root deployment and `/skillhub` runtime registry paths.

## Automated Verification

- Focused Vitest after review fixes: 4 files, 23 tests passed.
- Full Vitest after integrating the latest `origin/dev`: 232 files, 950 tests
  passed. The existing jsdom
  `Not implemented: navigation to another Document` notice remained
  informational.
- `corepack pnpm run typecheck`: passed.
- `corepack pnpm run lint`: passed with zero warnings.
- `corepack pnpm run build`: passed with 2,422 modules transformed. Existing
  runtime-config, Browserslist-age, and chunk-size notices remained
  informational.
- `corepack pnpm run test:e2e:subpath`: 26 Playwright tests passed across
  desktop Chromium and 390 x 844 mobile Chromium. The new coverage proves
  anonymous login return, selection, clear-focus recovery, reload persistence,
  protected install-page routing, Agent selection, exact `/skillhub` registry
  output, and no horizontal overflow.
- `git diff --check`: passed for the intended change.

## Real-Service Acceptance

The current source was built into the isolated `skillhub-oss-import-smoke`
Compose project. PostgreSQL, Redis, MinIO, scanner, FastAPI backend, root Web,
and `/skillhub` Web all reached `healthy`. Backend startup applied the existing
`skillhub_flyway_v43_baseline`, started the scan consumer, and logged no SQL
exception or traceback.

After integrating the latest `origin/dev`, the final commit was rebuilt as
`skillhub-web:oss-import-smoke` and both real-service Web containers were
recreated from that exact image. Root and `/skillhub` install routes, proxied
backend health routes, and the subpath runtime config all returned HTTP 200;
the running container image digest matched the newly built digest.

Authenticated browser acceptance verified:

- root URL `http://localhost:58080/install` retained two selected Skills after
  reload and focused the Install Skills heading;
- subpath URL `http://localhost:58082/skillhub/install` retained one selected
  Skill after reload and focused the heading;
- the subpath identity and install commands both used the exact registry
  `http://localhost:58082/skillhub`; and
- browser logs contained no warning or error from the feature. The only console
  entries were the existing i18next informational message.

The existing authenticated CLI download HTTP route was exercised against the
real FastAPI service with a 15-minute `skill:read` token. Two successful
downloads produced exactly two PostgreSQL `local_skill_download_event` rows:

| Event | Skill | Version row | Resolved version | User | Source |
| --- | ---: | ---: | --- | --- | --- |
| 1 | 123 | 167 | `20260825092850` | `docker-admin` | `cli` |
| 2 | 120 | 163 | `git-0c2cf683e796e276dd1244e00d0cf38bd2320637` | `docker-admin` | `cli` |

An invalid token returned 401 and a missing-Skill request failed before
download; neither created an event. The short-lived token (`api_token.id = 8`)
was revoked immediately. After acceptance PostgreSQL had zero
`idle in transaction` sessions; the observed distribution was one active
inspection session and six idle pooled connections.

## Security Boundary And Limitation

The generated public npm command was verified in browser output and the real
backend route/event path was verified directly. A success run did not hand the
fresh bearer to an `npx`-downloaded external package process because the tool
safety review rejected that secret exposure. This is not an application-code
gap: the Web emits no token, and the existing CLI-authenticated download route
is the unchanged tracking boundary. A separately approved external-package
acceptance may be run later with another short-lived token if policy requires
literal npm-process coverage.

## Review Resolution

- Persisted state is withheld until the authenticated owner is bound, avoiding
  a cross-identity first render.
- Rehydration deduplicates canonical coordinates before applying the 20-Skill
  cap.
- Install route entry, install clear, and search clear all restore useful
  focus.
- Workflow implementation lives in `features/install-selection`; the route
  page is only a re-export.
- Conditional classes use `cn()`, repeated login/coordinate logic was removed,
  and the unused toggle action was deleted.
- Durable Playwright coverage supplements focused component/store tests and
  the real-service browser acceptance.

The verified change was committed only after the user approved integration.

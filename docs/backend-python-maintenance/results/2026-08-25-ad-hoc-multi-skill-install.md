# Ad Hoc Multi-Skill Install Verification

Date: 2026-08-25

## 2026-08-27 Terminal Interactive Target Follow-up

The authenticated Install page now keeps **Direct Agent** as its default and
adds an opt-in **Terminal interactive** mode. Direct mode still requires one
explicit supported Agent. Interactive mode keeps the Web-selected Scope and
`--force`, omits `--agent`, enables copy-all and per-Skill copy, and visibly
states that every Skill opens its own target prompt, multiple Agents and
Generic may be selected, existing target directories are replaced, and the
mode is not for CI or background jobs.

The mode is stored in the existing authenticated tab-scoped selection state.
The persistence envelope advanced to version 3; older versions migrate to the
safe Direct default. Switching modes retains the direct Agent choice. English,
Simplified Chinese, and Traditional Chinese expose the same behavior, and the
bilingual Docusaurus feature manual documents both paths.

TDD and automated verification passed:

- focused Vitest: 3 files, 19 tests;
- full Vitest: 232 files, 958 tests;
- `corepack pnpm run typecheck`;
- `corepack pnpm run lint`;
- `corepack pnpm run build` with 2,422 modules transformed;
- Simplified Chinese and English Docusaurus production builds; and
- `corepack pnpm run test:e2e:subpath`: 28/28 desktop/mobile tests.

The first mobile integration run correctly caught the new warning pushing the
selected-Skills summary to 906 px in an 844 px viewport. Method and Scope were
recomposed into a compact two-column mobile grid without removing any warning.
The focused desktop/mobile seam then passed 2/2, and the full E2E suite retained
the initial-viewport and no-horizontal-overflow guarantees.

The exact updated Web source was built as `skillhub-web:oss-import-smoke`
(`sha256:38d38122ccadd55fd4d7eee5083ba9a5ce7c3ef3096f6f2f73a30f3a20a12e67`)
and recreated in both root and `/skillhub` containers. PostgreSQL, Redis, MinIO,
scanner, FastAPI, root Web, and subpath Web were healthy. Root `/install`,
subpath `/skillhub/install`, and backend health returned HTTP 200. Recent
backend/Web logs contained no SQL, traceback, exception, or nginx error, and
PostgreSQL reported zero `idle in transaction` sessions.

Real 390 x 844 in-app-browser acceptance measured the subpath multi-install
entry at 350.4 x 64 px with a 16 px page inset, no horizontal overflow, and no
browser warning/error. The temporary viewport override was reset and the test
tab was closed.

Finally, the exact public npm 0.1.9 interactive command shape was executed
against the real subpath registry with an isolated user home. Its shipped
target multiselect exposed both Codex and Generic; selecting both installed the
same Skill into the two contained target directories and created exactly one
new PostgreSQL download event (`id = 6`, `user_id = docker-admin`,
`source = cli`). The 15-minute validation token (`api_token.id = 13`) was
revoked, both isolated install directories and the temporary verifier were
removed, and no matching active token or temporary path remained.

## 2026-08-26 UX Discoverability Follow-up

The Search entry is now a large primary **Install multiple Skills** call to
action with an existing list-plus icon, visible “select up to 20 and copy
install commands” explanation, and forward affordance. Its accessible name
remains the concise action title. Equivalent copy is present in English,
Simplified Chinese, and Traditional Chinese.

The Install page selected-Skills disclosure is now open on first render. Its
summary uses the existing list/check, muted-surface, focus-ring, and chevron
patterns; the list remains collapsible and capped at three visible rows before
internal scrolling. Selection, command, tracking, API, and public CLI behavior
did not change.

Verification passed after the final responsive wrapper correction:

- focused Vitest: 3 files, 21 tests;
- full Vitest: 232 files, 956 tests;
- `corepack pnpm run typecheck`;
- `corepack pnpm run lint`;
- `corepack pnpm run build` with 2,422 modules transformed; and
- `corepack pnpm run test:e2e:subpath`: 28/28 desktop and mobile tests,
  including a dedicated Traditional Chinese layout case.

The final Web image
`sha256:2b9948fdd38663a55e60c682ce5609ea5b868bb390cc98fc3e3078d48eb47963`
ran in both root and `/skillhub` containers. PostgreSQL, Redis, MinIO, scanner,
FastAPI, root Web, and subpath Web were healthy; root Search, subpath Search,
and the FastAPI health endpoint returned HTTP 200. Recent backend and Web logs
contained no SQL, traceback, exception, or nginx error.

Real 390 x 844 browser acceptance measured the Traditional Chinese call to
action at 350.4 x 64 px in both root and `/skillhub`, with the normal 16 px page
inset, readable title/hint/icon/arrow composition, no horizontal overflow, and
no console error. The temporary viewport override was reset after acceptance.

## 2026-08-26 Compact Single-Agent Follow-up

This follow-up supersedes the original multi-Agent, optional-Force, terminal
identity, and install-page ordering decisions recorded below. The public npm
package `@astron-team/skillhub@0.1.9` rejects repeated explicit `--agent`
arguments with `multiple install targets detected`, so the Web workflow now
keeps multi-Skill selection but allows exactly one Agent target.

The compact workflow was verified with these results:

- the Skill checkbox renders immediately left of its title;
- the Search continuation action is sticky above the result list and remains
  within the initial desktop/mobile viewport;
- the Install page orders target controls, copyable commands, and a collapsed
  selected-Skills disclosure whose list is capped at three visible rows;
- commands always include one normalized `--agent` and `--force`;
- the Force control and terminal identity section are no longer rendered; and
- English, Simplified Chinese, and Traditional Chinese expose the same contract.

Automated verification passed:

- focused Vitest: 7 files, 66 tests;
- full Vitest: 232 files, 955 tests;
- `corepack pnpm run typecheck`;
- `corepack pnpm run lint`;
- `corepack pnpm run build` with 2,422 modules transformed; and
- `corepack pnpm run test:e2e:subpath`: 26/26 desktop and mobile tests.

The exact updated Web source was built as
`skillhub-web:oss-import-smoke` (`sha256:0103baf459c4e5555c03d1a73d0df21904516ef086037352a9b80464c08a05df`).
Both root and `/skillhub` containers ran that digest. PostgreSQL, Redis, MinIO,
scanner, FastAPI, root Web, and `/skillhub` Web were all healthy; the root and
subpath install routes returned HTTP 200. Browser checks found no console error
and confirmed the protected root/subpath routes retained the correct login
boundary.

Finally, the exact public-package shape was exercised against the real stack:

```text
npx @astron-team/skillhub@latest install alpha-smoke-skill \
  --namespace oss-skillhub-smoke-fixture-2641d1fab016 \
  --registry http://127.0.0.1:58082/skillhub \
  --scope project --agent codex --force --token <short-lived-token> --json
```

The command exited 0 and installed for the single `codex` target. PostgreSQL
recorded `local_skill_download_event.id = 5` for user `docker-admin`, source
`cli`, and resolved version `20260825092850`. The 15-minute validation token
(`api_token.id = 12`) was revoked immediately, the temporary project directory
was removed, and zero matching validation tokens remained active.

## Historical 2026-08-25 Baseline

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

## Historical Security Boundary And Limitation

The original run did not hand a bearer to an `npx`-downloaded package process.
That historical limitation is now closed by the 2026-08-26 short-lived-token
acceptance above; the token was revoked immediately after the literal public
npm package completed.

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

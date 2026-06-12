# Upstream Sync And Python Parity Workflow

Date: 2026-06-12

## Purpose

The Python backend now owns the default runtime after `backend-python-cutover-2026-06-12`, but the open-source upstream project can continue changing. This workflow keeps future upstream intake deliberate: compare upstream changes, classify impact, and port relevant behavior to Python with tests before launch.

## Canonical Remotes

| Remote | URL | Purpose |
| --- | --- | --- |
| `origin` | `https://github.com/brandonfang06/skillhub.git` | Working fork for branches and PRs. |
| `snapshot-fork` | `https://github.com/brandonfang06/skillhub-fork.git` | Snapshot/archive fork. |
| `upstream` | `https://github.com/iflytek/skillhub.git` | Canonical open-source upstream. Fetch only; push URL is disabled. |

## Cadence

- Fetch and run the drift report before each post-cutover hardening milestone batch.
- While the system is pre-launch, also check upstream at least weekly.
- Always run a drift report before merging the hardening branch back to `dev`.

## Drift Report Command

```powershell
git fetch upstream --prune
powershell -ExecutionPolicy Bypass -File scripts\check-upstream-backend-drift.ps1 -BaseRef upstream/main -HeadRef HEAD
```

Use another base or head ref only when documenting a specific intake window, for example:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-upstream-backend-drift.ps1 -BaseRef upstream/main -HeadRef dev
```

## Categories

The script groups changed files into:

- `java-backend-contract-or-behavior`
- `database-migration-or-schema`
- `frontend-or-api-client-expectation`
- `python-backend-runtime`
- `docs-config-or-ci`
- `scanner-cli-or-other-runtime`

The category is a starting point, not the final decision. Review file contents before deciding.

## Triage Decisions

Every upstream batch must record one decision per relevant change group:

- `port-to-python-now`: Required for security, schema, API contract, auth/authorization, lifecycle, publish/review, or data-integrity behavior.
- `accept-non-backend`: Appropriate for docs, frontend-only, config, or CI changes that do not change Python runtime behavior.
- `defer-with-reason`: Appropriate for non-critical Java-only cleanup or behavior outside current product scope.
- `reject`: Use only when an upstream change conflicts with the Python product direction.

## Porting Rules

- Java behavior changes must be ported by writing or updating Python tests first.
- Upstream Java Flyway migrations must become Python-owned schema migration work before launch.
- API contract or frontend client expectation changes must be reflected in Python route tests and, when relevant, web tests.
- Security, auth, token scope, session, lifecycle, publish, review, promotion, and data-integrity changes cannot be accepted as docs-only changes.
- Each accepted port must have a result note under `docs/backend-python-maintenance/results/` or the relevant migration result folder if it reopens a migration contract issue.

## Recommended Intake Steps

1. Fetch upstream.
2. Run `scripts\check-upstream-backend-drift.ps1`.
3. Inspect file contents for any non-zero high-impact category.
4. Write an intake note summarizing triage decisions.
5. For every `port-to-python-now` item, add or update Python tests first.
6. Implement the Python behavior.
7. Run targeted tests and full backend tests.
8. Record exact verification output in the result note.

## Current Baseline

As of 2026-06-12:

- `upstream/main`: `47765503915f0f9eaaff5ef65a50f08a1ccc34f5`
- Local hardening branch head when this workflow was added: `e40803dedcee1ae41f777cfa8e7e967c88e13111`
- Current drift report shows no `java-backend-contract-or-behavior` or `database-migration-or-schema` files in `upstream/main...HEAD`.

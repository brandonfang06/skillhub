# CLI Staging Smoke

Date: 2026-06-23

## Purpose

Add a live staging gate for the CLI path that was previously covered mainly by
backend route tests and CLI fake-registry integration tests. This catches
regressions where the TypeScript CLI and Python backend drift apart even though
each side still passes isolated tests.

## Flow

`scripts/cli-staging-smoke-test.sh` runs against a live Python staging backend:

1. register a normal local user;
2. create a real API token for that user;
3. create a namespace as bootstrap admin and grant the user membership;
4. run CLI dry-run publish through `bun src/index.ts`;
5. run CLI publish through `bun src/index.ts`;
6. wait for the Redis scan consumer to move the version out of `SCANNING`;
7. approve the review as bootstrap admin;
8. run CLI search and verify the approved package is visible;
9. run CLI install and verify `SKILL.md` plus SkillHub metadata are written.

`make cli-staging-smoke` reruns just this flow against an existing staging
backend. `make staging` now runs the basic smoke, publish/scan/download smoke,
and this CLI smoke.

## Verification

Passed:

```powershell
cd server-python
uv run pytest tests/test_staging_cli_smoke_contract.py -q
```

Result: `1 passed`.

Passed:

```powershell
cd server-python
uv run pytest tests -q
```

Result: `823 passed, 1 warning`.

Passed:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -n scripts/cli-staging-smoke-test.sh
git diff --check
```

Passed:

```powershell
$env:BOOTSTRAP_ADMIN_USERNAME='admin'
$env:BOOTSTRAP_ADMIN_PASSWORD='Admin@staging2026'
& 'C:\Program Files\Git\bin\bash.exe' scripts/cli-staging-smoke-test.sh http://localhost:8080
```

Result:

- CLI staging smoke: `13 passed`
- server log showed `Processing scan task` for the CLI-published version
- scanner log showed `POST /scan-upload HTTP/1.1" 200 OK`

Passed:

```powershell
cd cli
bun run typecheck
bun run lint
bun run test
```

Result: `331 pass, 6 skip, 0 fail`.

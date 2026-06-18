# Local Environment Template

Date: 2026-06-18

## Scope

Add a local development environment template so developers can override
dependency and backend settings without editing runtime source files or
`docker-compose.yml`.

## Changes

- Added `.env.local.example`.
- `.env.local` remains ignored by git through the existing `.env.*` ignore rule.
- The Python backend should be started directly with
  `uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload`; add
  `--env-file ../.env.local` when local overrides are needed.
- `docker-compose.yml` now accepts local overrides for PostgreSQL, Redis
  password, MinIO credentials, scanner LLM values, and dependency images while
  preserving the previous zero-config defaults.
- Python backend local defaults are filled only when env values are unset, so
  `.env.local` can override bootstrap admin and scanner behavior.
- `docs/dev-workflow.md` and `README.md` now explain local vs staging vs release
  env sources.

## Local Env Source Summary

| Runtime | Env source |
| --- | --- |
| Local backend | Optional `.env.local` through `uv run uvicorn ... --env-file ../.env.local` |
| Local dependencies | Optional `.env.local` through `docker compose --env-file .env.local` |
| `make staging` | `docker-compose.yml` + `docker-compose.staging.yml` |
| Release compose | `.env.release` + `compose.release.yml` |

## Verification

```powershell
cd server-python
uv run pytest tests/test_python_runtime_cutover.py -q
uv run pytest tests/test_python_runtime_cutover.py tests/test_deployment_cutover.py tests/test_config.py -q
uv run pytest tests -q
```

Results:

```text
8 passed in 0.04s
34 passed in 0.13s
780 passed, 1 warning in 58.05s
```

Compose rendering:

```powershell
docker compose -p skillhub-local-env-check config
Copy-Item .env.local.example .env.local.check
docker compose -p skillhub-local-env-check --env-file .env.local.check config
Remove-Item .env.local.check
docker compose --env-file .env.release.example -f compose.release.yml config
```

Results:

```text
dev compose config rendered without .env.local
dev compose config rendered with env local example
release compose config rendered
```

Static check:

```powershell
git diff --check
```

Result: no whitespace errors; only Windows LF-to-CRLF warnings.

## Not Verified

The Python backend is intentionally documented as a direct `uv run uvicorn`
process instead of a `make` target.

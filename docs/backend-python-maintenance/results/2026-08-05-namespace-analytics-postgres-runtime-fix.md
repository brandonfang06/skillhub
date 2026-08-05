# Namespace Analytics PostgreSQL Runtime Fix

**Date:** 2026-08-05
**Branch:** `codex/fix-namespace-analytics-postgres`
**Status:** Verified against the complete local runtime stack

## Incident

The first deployment of Namespace Analytics returned HTTP 500 for every
analytics request. The page displayed its generic preserved-filter error state,
while the backend logged:

```text
asyncpg.exceptions.AmbiguousParameterError:
could not determine data type of parameter $1
```

The query used nullable SQLAlchemy text binds in expressions such as
`(:namespace_type IS NULL OR n.type = :namespace_type)`. PostgreSQL prepares
the statement before receiving runtime values and could not infer the bind
type from the `IS NULL` expression.

## Why Pre-merge Verification Missed It

- Backend tests used a fake connection that inspected SQL text and returned
  prepared rows; PostgreSQL never parsed or executed the aggregation query.
- Production-bundle browser tests used a controlled analytics API fixture.
- Typecheck, lint, build, and OpenAPI checks cannot validate PostgreSQL
  statement preparation.
- The implementation result listed organization PostgreSQL acceptance as a
  remaining runtime gate, but that gate was not completed before merge.

Mock and fixture coverage remains useful, but it must not be described as
complete verification for a database-backed feature.

## Fix

All optional text filters in the shared aggregation CTE now use explicit
PostgreSQL `text` casts: namespace type, namespace status, namespace query, and
download source. The API contract, frontend contract, schema, and environment
variables are unchanged.

A PostgreSQL-backed regression test now executes the real repository query
when `SKILLHUB_TEST_DATABASE_URL` is set. The test failed with the deployed
`AmbiguousParameterError` before the fix and passed after the casts were added.

## Live Service Evidence

The local validation stack includes:

- PostgreSQL 16;
- Redis 7;
- MinIO;
- the Python scanner;
- the current FastAPI backend;
- the production Nginx frontend image; and
- a prefix-rewrite proxy equivalent to the production Istio `/skillhub`
  rewrite.

The backend image ran the Python migration upgrade before starting Uvicorn.
Its migration output was `skillhub_flyway_v43_baseline`; the database's latest
Flyway history row remained version `42`, as expected for the existing local
baseline. The same default-filter request changed from HTTP 500 to HTTP 200
against PostgreSQL.

The real browser flow then used the production frontend bundle at
`http://localhost:3000/skillhub/admin/namespace-analytics`, retained an
authenticated local super-administrator session, and rendered the
database-backed page. It applied the Global namespace type, `global` query,
and CLI source filters. The URL retained all filters across reload, the table
contained the single matching Global row, and the browser reported no console
warnings or errors.

During the container check, old host Vite and Uvicorn processes were found to
be intercepting ports 3000 and 8080 even though the containers were running.
They were identified by PID and command line and stopped before the final
checks. This is an important verification guard: container existence alone
does not prove that test traffic reached the container.

## Verification Results

The PostgreSQL regression test was demonstrated red/green:

- before the production cast fix: failed with
  `asyncpg.exceptions.AmbiguousParameterError`;
- after the fix: `1 passed in 0.42s`.

Fresh full-suite and build results:

- backend with `SKILLHUB_TEST_DATABASE_URL` pointing at PostgreSQL 16:
  `1160 passed` in `144.90s` with one existing Starlette deprecation warning;
- Python compilation: `python -m compileall app tests` passed;
- frontend Vitest: `203` files and `786` tests passed;
- frontend typecheck: passed;
- frontend ESLint: passed with zero errors and warnings;
- frontend production build: passed with the existing runtime-config,
  Browserslist, and large-chunk warnings;
- production subpath Playwright: `16 passed` across desktop and mobile;
- backend image:
  `sha256:0c351d1df9987fa395c7ae6b2e36db805f9401367edd0ac63b9e1ec7ae100e17`;
- web image:
  `sha256:e8f9e535ff7e2fa78c44e8642f963be96bf3abfc868f2bff8dda8022801e2efd`.

Live integration checks after host-process isolation:

- PostgreSQL query and `/skillhub/api/v1/admin/namespace-analytics`: HTTP 200;
- Redis: `PONG` from its container and `True` from the backend's configured
  async Redis client;
- MinIO health from the host and from the backend container: HTTP 200;
- scanner health from the host and from the backend container: HTTP 200;
- backend health: HTTP 200;
- web and prefix proxy health: HTTP 200;
- production bundle, runtime config, lazy Namespace Analytics chunk,
  authenticated API calls, filters, and reload all passed through the
  `/skillhub` rewrite path.

The complete stack remains running for manual acceptance at
`http://localhost:3000/skillhub/`.

## Verification Requirement Going Forward

For a new or changed feature, verification must start every related runtime
dependency and exercise the real integration boundary. Database-backed work
must run migrations and execute the changed SQL against PostgreSQL. Scanner,
Redis, storage, authentication, and deployment routing must also be live when
the feature depends on them. Mock-only or fixture-only checks may supplement
this gate but cannot replace it.

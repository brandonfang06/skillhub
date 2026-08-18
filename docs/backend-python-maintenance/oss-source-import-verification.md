# OSS GitHub source import verification

Date: 2026-08-18 (Asia/Taipei)

Branch: `codex/oss-source-import`

This record covers the GitLab-runner OSS GitHub source import flow described by:

- `plans/2026-08-18-oss-github-source-import-gitlab-design.md`
- `plans/2026-08-18-oss-github-source-import-gitlab-implementation.md`

## Runtime used

The final smoke ran against the isolated Compose project
`skillhub-oss-import-smoke`, with the following real services healthy at the
same time:

| Service | Verification endpoint or port |
| --- | --- |
| PostgreSQL 16 | `127.0.0.1:55432` |
| Redis 7 | `127.0.0.1:56379` |
| MinIO | internal S3 endpoint `http://minio:9000` |
| Python backend | `http://localhost:58081` |
| scanner | internal `http://skill-scanner:8000` |
| root-path web/proxy | `http://localhost:58080` |
| `/skillhub` web/proxy | `http://localhost:58082/skillhub` |

The migration command was also rerun successfully inside the backend image:

```powershell
docker compose -p skillhub-oss-import-smoke --env-file .env.release.example `
  -f compose.release.yml -f docker-compose.oss-source-import-test.yml `
  exec -T server .venv/bin/python -m app.migrations upgrade
```

Result: `skillhub_flyway_v43_baseline`.

The final verification images were:

- `skillhub-server-python:verify`: `sha256:c121366ad85e9242765bbd0741bcbeb6e59ff0a6d7d6cac33aea0ede5f3fbb67`
- `skillhub-oss-source-importer:verify`: `sha256:0a5960d8b4717e678128d199b0bdd51769f124f81b0f63f9074c5964110916ff`

## Automated checks

### Backend

The source-import suite ran against PostgreSQL with integration tests enabled:

```powershell
cd server-python
uv run --no-cache pytest tests/test_source_import_*.py `
  tests/test_oss_source_*.py tests/test_publish_*.py `
  tests/test_review_skill_detail.py tests/test_skill_version_detail*.py -q
```

Result: `72 passed, 1 warning` and no source-import integration skips.

The complete Python backend suite then passed against PostgreSQL:

```powershell
uv run --no-cache pytest tests -q
```

Result: `1403 passed, 10 skipped, 1 warning in 170.85s`. The remaining skips
are pre-existing, unrelated optional cases; the new PostgreSQL source-import
tests ran.

### Importer

```powershell
cd tools/oss-source-importer
uv run pytest -q
uv run ruff check .
uv build
docker build -q -t skillhub-oss-source-importer:verify `
  -f Dockerfile .
```

Result: `18 passed`; Ruff passed; source distribution and wheel built; image
built and its CLI help command ran successfully.

### Frontend and subpath

```powershell
cd web
pnpm run typecheck
pnpm run lint
pnpm test -- --run
pnpm run build
pnpm exec playwright test e2e/subpath-deployment.spec.ts
```

Results:

- typecheck passed;
- lint passed;
- Vitest: `215 files, 868 tests passed`;
- production Vite build passed;
- Playwright root/subpath matrix: `20 passed (58.6s)` on desktop and mobile Chromium.

The subpath test includes the public immutable GitHub provenance link and keeps
all API requests under the configured `/skillhub` base.

### Deployment rendering

```powershell
docker build -q -t skillhub-server-python:verify -f server-python/Dockerfile .
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
docker compose --env-file .env.release.example -f compose.release.yml `
  -f docker-compose.oss-source-import-test.yml config
```

Result: backend image build, K8s render, release Compose render, and test
overlay Compose render all passed.

## Final full-stack smoke

Command:

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts/oss-source-import-smoke-test.ps1
```

Final result at 2026-08-18 16:41 +08:00:

```text
OSS source import smoke passed: run=e4f09b244b0d initial=ad433c60fb34e6a628abb1f0ccd64ef426850e5a changed=7ef49f31ba63ee0c22d9f598ef18614ef9a2ba9c
```

The smoke performed and asserted all of the following through the public Nginx
routes:

1. copied a committed fixture to a unique temporary checkout and made a real Git commit;
2. created unique OAuth-style identity bindings, importer actor, role, and `source:import` token in PostgreSQL;
3. derived the OSS namespace and submitted three independent deterministic ZIP packages;
4. proved stable skill owner, review submitter, and importer audit actor are distinct and correct;
5. waited for the real Redis consumer and scanner to create review and security-audit evidence;
6. verified package objects exist in MinIO;
7. read provenance in namespace review, approved one version through the normal review API, and read the same immutable commit provenance publicly;
8. retried the identical revision and received only skip outcomes;
9. committed a change to only the unversioned Alpha fixture, imported through `/skillhub`, and received exactly `git-7ef49f31ba63ee0c22d9f598ef18614ef9a2ba9c` for Alpha while unchanged skills skipped;
10. proved the second trigger became the new review submitter without transferring the existing stable skill owner.

The final three-minute log window for PostgreSQL, Redis, MinIO, scanner,
backend, root web, and subpath web contained no traceback, scanner task failure,
SQL syntax error, unhandled exception, fatal, panic, or error entry.

The isolated Compose project remains running so the feature can be inspected
before merge. Its uniquely named smoke rows and S3 objects are confined to the
test database and bucket; no shared or production service was modified.

## Scope review

The branch diff was reviewed against the approved design. It contains no Java,
Maven, Spring Boot, source-repository fetcher, auto-publish path, ordinary-token
default-scope expansion, skill-owner transfer on later runs, removed-skill
deletion, or production MinIO/K8s workload. Scanner and namespace-owner review
remain mandatory.

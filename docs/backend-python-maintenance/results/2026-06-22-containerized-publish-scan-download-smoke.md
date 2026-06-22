# Containerized Publish Scan Download Smoke

Date: 2026-06-22

## Purpose

Add a staging smoke gate that exercises the deployment topology that previously
let scanner and object-storage regressions slip through:

1. register a normal local user and log in as bootstrap admin;
2. create a namespace as admin and grant the user membership;
3. publish a skill package as the namespace user;
4. verify the Redis scan consumer processes the task through the scanner
   container;
5. verify security audit evidence is recorded;
6. approve the review as admin;
7. download the approved package from object storage.

## Changes

- `docker-compose.staging.yml` now enables `SKILLHUB_SCAN_CONSUMER_ENABLED=true`.
- Staging now uses MinIO/S3 storage instead of local-only storage, with
  auto-create bucket enabled for local staging verification only.
- `scripts/publish-scan-download-smoke-test.sh` implements the full
  publish -> scan -> review -> download flow without relying on mock users.
- `make staging` now runs the existing basic smoke and the new publish/scan
  smoke. `make publish-scan-smoke` can rerun just the new smoke against a
  running staging backend.

## Verification

Passed:

```powershell
cd server-python
uv run pytest tests/test_staging_publish_scan_smoke_contract.py tests/test_deployment_cutover.py -q
```

Result: `12 passed`.

Passed:

```powershell
cd server-python
uv run pytest tests -q
```

Result: `822 passed, 1 warning`.

Passed:

```powershell
docker build -t skillhub-server-python:staging -f server-python/Dockerfile .
cd web
pnpm run build
```

Passed:

```powershell
docker compose -p skillhub-staging up -d --wait
docker compose -p skillhub-staging exec -T postgres psql -U skillhub -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS skillhub WITH (FORCE);"
docker compose -p skillhub-staging exec -T postgres psql -U skillhub -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE skillhub;"
docker compose -p skillhub-staging -f docker-compose.yml -f docker-compose.staging.yml up -d --wait server web
```

Passed:

```powershell
$env:BOOTSTRAP_ADMIN_USERNAME='admin'
$env:BOOTSTRAP_ADMIN_PASSWORD='Admin@staging2026'
& 'C:\Program Files\Git\bin\bash.exe' scripts/smoke-test.sh http://localhost:8080
& 'C:\Program Files\Git\bin\bash.exe' scripts/publish-scan-download-smoke-test.sh http://localhost:8080
```

Result:

- basic smoke: `14 passed, 0 failed`
- publish/scan/download smoke: `11 passed`
- server log showed `Creating scan consumer daemon` and `Processing scan task`
- scanner log showed `POST /scan-upload HTTP/1.1" 200 OK`

## Notes

The local machine did not have `make`; the staging target was validated by
running the equivalent commands directly. Existing dev dependency containers
were stopped without deleting volumes before starting the isolated staging
compose project because their published host ports conflicted with staging.

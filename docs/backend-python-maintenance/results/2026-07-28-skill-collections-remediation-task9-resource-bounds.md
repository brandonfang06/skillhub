# Skill Collections Remediation Task 9: Resource Bounds

Date: 2026-07-28

## Outcome

Repository import and collection install now have explicit resource boundaries:

- repository ZIP: 500 files, 5 MiB per expanded file, 50 MiB total expanded;
- import preview: 100 discovered Skill candidates;
- collection draft/manifest: 100 exact-version members;
- CLI collection archives: loaded and extracted one package at a time.

Repository ZIP parsing runs through `asyncio.to_thread` in preview, ingest
verification, and update checks. The ingest archive SHA-256 check still runs
before parsing. Existing traversal, symlink, duplicate-path, exact-version,
preflight, filesystem rollback, inventory rollback, and atomic inventory write
boundaries remain in place.

## TDD Evidence

Before implementation, backend collection tests stopped on the missing shared
member-limit constant. CLI tests reported:

```text
15 pass, 2 fail
```

The CLI failures proved that a 101-member manifest reached the transaction and
that both package archives were loaded before the first extraction.

After implementation:

```text
server-python\.venv\Scripts\pytest.exe \
  tests/test_config.py \
  tests/test_repository_import_archive.py \
  tests/test_repository_import_service.py \
  tests/test_collection_mutations.py \
  tests/test_repository_import_api.py \
  tests/test_deployment_cutover.py -q

108 passed, 2 warnings
```

```text
bun test \
  test\unit\services\collection-install-service.test.ts \
  test\unit\services\install-transaction.test.ts

17 passed, 0 failed, 57 expect() calls
```

The warnings were the existing Starlette `httpx` deprecation notice and the
intentional duplicate-ZIP-entry warning in the archive security test.

## Availability Check

A local, no-network check parsed an archive at both configured maxima:

```text
files: 500
expandedBytes: 52428800
healthRequestsDuringParse: 25
healthCodes: [200]
```

All 25 `/api/v1/health` requests completed while archive parsing was still in
progress. Over-limit archive/candidate service errors use HTTP 413 before
preview persistence or publication. HTTP request contracts reject a
101-member collection/candidate payload before the route writer runs; the
repository-import seed service also fails with 413 before reading members.
The CLI rejects a 101-member manifest before any package transaction or
filesystem mutation.

## Deployment Verification

The four backend variables are present in release Compose, K8s base/plain
ConfigMaps and pod env wiring, and both operator references:

```text
SKILLHUB_GITLAB_ARCHIVE_MAX_FILES=500
SKILLHUB_GITLAB_ARCHIVE_MAX_SINGLE_FILE_BYTES=5242880
SKILLHUB_GITLAB_ARCHIVE_MAX_EXPANDED_BYTES=52428800
SKILLHUB_GITLAB_IMPORT_MAX_CANDIDATES=100
```

`kubectl kustomize deploy\k8s\base` and
`docker compose --env-file .env.release.example -f compose.release.yml config
--quiet` both exited 0. Docker printed a sandbox-only warning that the user
Docker config was unreadable; manifest rendering still completed.

No real GitLab request, deployment, flag enablement, commit, push, or PR was
performed.

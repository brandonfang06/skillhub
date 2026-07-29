# No-Anonymous Skill Content Result

**Date:** 2026-07-29
**Branch:** `codex/download-auth-hardening`
**Status:** Implementation and verification complete; not committed or merged

## Outcome

SkillHub now requires a real browser session or bearer token before returning
skill content. This is unconditional and cannot be disabled by configuration.

Protected content includes:

- latest, version, and tag package downloads through API, web, and CLI aliases;
- version and tag raw file content through API and web aliases;
- version compare output, because it contains changed file content;
- review packages, review raw files, and review skill detail containing
  `documentationContent`.

`X-Mock-User-Id` is not accepted by these content routes. PUBLIC search,
skill detail, version/file-name metadata, and resolve data remain anonymously
available under the existing visibility and lifecycle rules.

Repository readers independently reject missing or blank user ids before
version/file lookup, storage I/O, counters, or analytics. Authenticated access
then retains the existing policy:

- PUBLIC: any authenticated user;
- NAMESPACE_ONLY: namespace members;
- PRIVATE: skill owner or namespace manager;
- UPLOADED/PENDING_REVIEW content: skill owner or namespace manager only;
- CLI package download: ready, non-yanked PUBLISHED versions only.

`SKILLHUB_DOWNLOAD_REQUIRE_AUTH` was removed. Setting it to `false` has no
effect and no Compose or Kubernetes artifact exposes it.

## Review Findings Fixed

1. Production auth trusted caller-controlled `X-Mock-User-Id`. A caller could
   spoof an existing administrator id and download content. Content routes now
   ignore that header and accept only session or bearer identity.
2. Version compare reads changed files and returns diff content. It now uses
   the same content-authentication boundary instead of optional identity.
3. Review skill detail embeds `documentationContent`. Review package, raw
   file, and skill-detail routes now reject anonymous and mock-only callers.
4. Repository defense treated an empty string user id as authenticated for a
   PUBLIC skill. Missing and blank ids are now both denied.
5. The ClawHub query redirect did not forward bearer identity into legacy
   coordinate resolution. It now preserves authenticated private/team lookup
   while the redirected package route remains protected.

The review also confirmed that successful PUBLISHED package downloads alone
increment counters and analytics. Denied package attempts and raw/compare
reads do not create download events.

## Verification

Backend:

```text
focused content, review, CLI-flow, and metadata regression set:
145 passed

configuration and deployment tests:
38 passed

complete backend suite:
1005 passed, 1 existing Starlette/httpx deprecation warning
```

CLI:

```text
bun test
346 pass, 6 skip, 0 fail
```

The CLI suite covers login/token precedence, unauthenticated install failure,
bad-token failure without anonymous retry, authenticated download, extraction,
publish, and search behavior.

Deployment and image:

```text
kubectl kustomize deploy\k8s\base
success

docker compose --env-file .env.release.example -f compose.release.yml config --quiet
success

docker build -t skillhub-server-python:no-anonymous-content-verify -f server-python/Dockerfile .
image manifest: sha256:a62dcf80698ce462f31efeb04ae3329cdd7dbcc7c81b2606e18e458366b9ee40
```

## Live Isolated Scenario

The reviewed image ran at `127.0.0.1:18080` against the retained isolated
PostgreSQL/Redis test stack and a read-only mount of the task-specific local
skill storage.

Observed behavior for a published PUBLIC skill:

```text
anonymous skill detail:             200
anonymous package:                  401
mock-header package spoof:          401
anonymous raw file:                 401
mock-header raw file spoof:         401
anonymous version compare:          401
mock-header review content spoof:   401
download events after denials:      1 -> 1

session registration:               200
session package:                    200, 396 bytes
session raw file:                   200, 164 bytes
download events after package:      1 -> 2
```

An authenticated compare request reached the repository and returned the
expected domain `400` for a deliberately missing comparison version, proving
authentication no longer blocked valid callers.

The backend and the three dependency containers started for this verification
were stopped. Ports `5432`, `6379`, `9000`, `9001`, and `18080` were released.
Containers, volumes, the `.dev` storage, and the isolated test records were
preserved.

The live scenario preceded the final ClawHub redirect-only bearer-forwarding
fix. That fix does not change content authorization; it was verified through a
dedicated RED/GREEN route test, the final `1005`-test backend suite, and the
final image rebuild recorded above.

## Compatibility

- Anonymous CLI/OpenClaw installs now fail with login guidance.
- Logged-in browser downloads continue through the session cookie.
- CLI downloads continue through stored bearer tokens.
- PUBLIC metadata remains anonymously discoverable.
- Historical anonymous analytics rows are not rewritten.
- Object storage must remain private; SkillHub does not generate direct or
  presigned package URLs.

The checked-in frontend OpenAPI generator still targets the removed Java
`/v3/api-docs` endpoint while FastAPI serves `/openapi.json`. Regenerating from
FastAPI would create a broad unrelated schema replacement, so generated
frontend types were not changed. Route contracts are covered directly by the
backend tests.

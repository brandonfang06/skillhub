# OSS Import Internal Network Compatibility

Date: 2026-08-26

Status: Implemented and verified locally

## Decisions

### Credentialed Dev GitLab clone URL

`SKILLHUB_DEV_GITLAB_REPOSITORY_URL` may contain URL username/password
credentials. The importer removes userinfo before adding the Git remote or
writing job logs, decodes the credentials, and supplies them only through the
temporary Git subprocess `Authorization` header. URL credentials take
precedence over `CI_JOB_TOKEN`; a credential-free URL continues to use the job
token. HTTPS remains required.

The credentialed URL still exists in the protected `pull-code.env` artifact, so
artifact access and retention must be restricted. Credentials must never appear
in Git command arguments, the temporary remote URL, reports, errors, or job
logs.

### SkillHub API TLS

The central importer disables certificate and hostname verification for HTTPS
requests to `SKILLHUB_BASE_URL`. Redirects remain disabled and HTTP behavior is
unchanged. This is an accepted internal-network tradeoff: the `st_` service
token and imported package are no longer protected against an active internal
TLS interception endpoint.

This bypass applies only to the Python SkillHub API client. GitLab clone TLS
verification is unchanged and may still use the runner trust store or
`SSL_CERT_FILE`.

### Namespace owner provider

`SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE` is removed from project/group
variables and importer configuration. Source namespace fallback-owner requests
use the deployment's fixed SkillHub identity provider code `keycloak`.
`SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE` remains optional and defaults to
`keycloak`.

## Verification

- Config accepts credentialed HTTPS Dev GitLab URLs and still rejects HTTP,
  query, fragment, and malformed URLs.
- Clone tests prove decoded URL credentials are used only in subprocess
  environment and are absent from arguments, errors, reports, and logs.
- An HTTPS loopback test with an untrusted certificate proves the SkillHub
  client succeeds without certificate verification while redirects remain
  blocked.
- Config, template, smoke, and operator tests prove the namespace owner provider
  variable is absent and `fallbackOwnerProviderCode` remains `keycloak`.
- The stock Python 3.8 runner and complete real-service smoke remain required.

## Verification Results

- `uv --no-cache run pytest -q -p no:cacheprovider`: 56 passed and the
  OpenSSL-dependent HTTPS test skipped on the Windows host.
- The self-signed HTTPS runtime probe passed in `python:3.8-bookworm` with
  `python -S`, after first proving the same certificate fails default
  verification.
- `uv --no-cache run ruff check src tests`: passed.
- `server-python`: `uv --no-cache run pytest tests/test_oss_source_import_docs.py
  -q -p no:cacheprovider`: 4 passed.
- `scripts/oss-source-import-smoke-test.ps1 -KeepTemporaryRoot`: passed against
  the real seven-service stack for run `a7322a11f811`, including credentialed
  Dev clone redaction, first import, retry, changed import, root and `/skillhub`
  routing, PostgreSQL, Redis, MinIO, scanner, review, and provenance evidence.

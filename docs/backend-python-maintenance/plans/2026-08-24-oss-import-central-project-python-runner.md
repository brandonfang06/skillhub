# OSS Import Internal GitLab Self-Clone Python Runner

Date: 2026-08-24

Status: Corrected implementation verified; awaiting commit authorization

## Decision

The GitHub repository is already migrated into an internal GitLab source
project before this stage runs. A user starts a pipeline in that project and
provides the original HTTPS GitHub repository URL only as upstream identity.
The project-local shell wrapper starts project-local Python code. Python clones
the current internal GitLab project through `CI_REPOSITORY_URL`, checks out the
exact `CI_COMMIT_SHA`, discovers and packages every exact-case `SKILL.md` root,
and calls the existing SkillHub source-import APIs with a platform-managed
`st_` service token.

The GitLab job does not use the TypeScript/Bun SkillHub CLI, an installed
`skillhub-oss-import` console command, curl-based upload orchestration, or an
importer-specific OCI image. Importer behavior changes ship with the GitLab
project source and therefore do not require rebuilding an importer image.

## Runtime boundary

The GitLab runtime image is a stable organization-approved toolchain image. It
must provide:

- Python 3.12;
- Git;
- CA certificates and any organization trust bundle; and
- a POSIX shell for the GitLab job script.

It does not contain SkillHub importer code. The importer code is checked out as
part of the current GitLab source project. Runtime Python dependencies are installed
from the project's locked dependency file, using the organization's configured
Python package mirror when required.

The call chain is:

```text
GitLab Runner shell
  -> deploy/gitlab/oss-source-import.sh
  -> python tools/oss-source-importer/run_import.py
  -> git clone current internal GitLab CI_REPOSITORY_URL at CI_COMMIT_SHA
  -> Python discovery, deterministic ZIP, and HTTP API client
  -> public SkillHub reverse proxy/Ingress
  -> Python FastAPI source-import endpoints
```

## Source and provenance contract

`CI_PROJECT_DIR`, `CI_REPOSITORY_URL`, and `CI_COMMIT_SHA` describe the current
internal GitLab source project. `CI_REPOSITORY_URL` is the actual clone
coordinate and may contain a short-lived job token, so it is never reported or
sent to SkillHub.

The required `SKILLHUB_SOURCE_REPOSITORY_URL` remains restricted to
credential-free `https://github.com/<owner>/<repo>[.git]` URLs. It is used only
for upstream provenance and deterministic namespace naming. Runner does not
connect to GitHub and never clones this URL.

Python shallow-fetches `CI_COMMIT_SHA` from the internal GitLab project and
verifies the detached checkout with `git rev-parse HEAD`. `CI_COMMIT_TAG` takes
precedence as TAG, otherwise `CI_COMMIT_BRANCH` identifies a BRANCH; a detached
pipeline is recorded as COMMIT. The GitLab pipeline ref selector chooses the
source ref, so there is no separate `SKILLHUB_SOURCE_REF` variable.

Backend provenance and the deterministic `git-<40-char-source-commit>` fallback
version use the verified internal GitLab commit. For a GitHub exact-commit link
to remain valid, the GitHub-to-GitLab migration must preserve Git history and
commit SHA.

`SKILLHUB_IMPORT_SOURCE_ROOT`, when present, is a relative path inside the
cloned repository. Absolute paths and paths escaping the checkout are rejected.

## Preserved backend and governance behavior

No backend endpoint or authorization change is required. The runner-side Python
continues to call:

- `PUT /api/cli/v1/source-imports/namespaces/{namespaceSlug}`;
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills/validate`; and
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills`.

The endpoints still require an `st_` service token with `source:import`.
Initiator attribution, fallback owner behavior, stable skill ownership,
scanner execution, namespace-owner review, idempotent skips, and no direct
publication remain unchanged.

The backend never clones GitHub repositories and never receives GitHub
credentials. The importer never writes directly to PostgreSQL, Redis, MinIO, or
the scanner.

## GitLab variables

Required:

- `SKILLHUB_PYTHON_IMAGE`: immutable Python 3.12 + Git runtime image;
- `SKILLHUB_BASE_URL`;
- `SKILLHUB_SERVICE_TOKEN`;
- `SKILLHUB_SOURCE_REPOSITORY_URL`;
- `SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE`;
- `SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME`.

Optional:

- `SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE`;
- `SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME`;
- `SKILLHUB_IMPORT_SOURCE_ROOT`;
- `SKILLHUB_IMPORT_REPORT_PATH`;
- `SKILLHUB_IMPORT_TIMEOUT_SECONDS`;
- standard Python package-index variables such as `PIP_INDEX_URL` and
  `PIP_CERT` when the organization requires an internal mirror;
- `SSL_CERT_FILE` for SkillHub/internal GitLab TLS trust where required.

GitLab supplies `CI_REPOSITORY_URL`, `CI_COMMIT_SHA`, `CI_COMMIT_TAG`,
`CI_COMMIT_BRANCH`, `CI_COMMIT_REF_NAME`, `CI_PIPELINE_ID`, and `CI_JOB_ID`.
The credentialed clone URL remains local; commit/ref and pipeline/job IDs appear
in the JSON report for provenance and traceability.

## Verification contract

- Tests prove exact-commit internal GitLab self-clone, GitLab branch/tag/commit
  metadata, checkout SHA verification, temporary-directory containment, no
  submodules, safe source-root resolution, credential redaction, and clone
  failure mapping.
- GitLab template tests prove the stage uses `SKILLHUB_PYTHON_IMAGE` and the
  project-local shell wrapper, with no importer image or installed SkillHub CLI.
- Shell tests prove it invokes the project-local Python runner and locked
  dependency setup without curl-based upload logic.
- Existing package, orchestration, API, identity, ownership, review, scanner,
  idempotency, and report tests remain green.
- A real-service smoke runs PostgreSQL, Redis, MinIO, scanner, Python backend,
  root and `/skillhub` proxies, then executes the exact shell/Python clone path.

## Non-goals

- No GitHub credentials, Runner-side GitHub fetch, GitHub Enterprise, SSH clone
  URLs, webhooks, or backend-side fetch.
- No SkillHub TypeScript CLI or OAuth Device Flow in the pipeline.
- No importer-specific OCI image requirement.
- No curl implementation of multipart source-import requests.
- No direct publication, scanner bypass, review bypass, owner transfer, or
  deletion of skills missing from a later source checkout.

## Verification result

The earlier GitHub-clone verification is superseded by this correction. The
final smoke used a generic Python/Git image, a GitLab-shaped credentialed
`CI_REPOSITORY_URL`, exact `CI_COMMIT_SHA`, and the complete PostgreSQL, Redis,
MinIO, scanner, backend, root proxy, and `/skillhub` topology. Run
`1427888a4efb` passed, the simulated job token was absent from the report, and
the final service log scan returned zero errors.

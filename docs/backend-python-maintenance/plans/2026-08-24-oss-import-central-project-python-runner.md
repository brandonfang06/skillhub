# Central OSS Import Pipeline Runner

Date: 2026-08-24

Status: Implemented and verified on 2026-08-25

## Decision

The organization runs OSS intake from one central `pull_pipeline` repository.
`pull-pipeline-for-user` triggers that pipeline. Its existing `pull_code` job
accepts only scan-passed content, lands it on a protected Dev GitLab branch, and
emits a dotenv handoff. A following `publish_skillhub` job clones that Dev GitLab
project and branch and calls the existing SkillHub source-import endpoints.

The publish job never clones the external GitHub or OSS GitLab source. It also
does not treat the central pipeline's own GitLab checkout variables as source
coordinates.

## Call chain

```text
pull-pipeline-for-user
  -> central pull_pipeline
  -> scan
  -> pull_code
       -> protected Dev GitLab project and branch
       -> pull-code.env
  -> publish_skillhub
       -> repository-owned Python importer
       -> Dev GitLab branch checkout
       -> SkillHub source-import endpoints
  -> SkillHub scanner and namespace-owner review
```

## Runtime seam

GitLab Runner checks the central repository out at `CI_PROJECT_DIR`. The shell
wrapper and Python source run from that checkout; they are neither mounted nor
copied into the runtime image.

The immutable organization image must provide Python 3.8, Git, CA certificates,
and a POSIX shell. The importer uses the Python standard library for HTTP,
multipart, JSON, TLS, and timeout handling. The production job performs no
`pip install`, dependency synchronization, or importer-image build. `pytest`
and `ruff` remain development-only dependencies.

## Handoff interface

`pull_code` publishes the following trusted dotenv values:

- `SKILLHUB_SOURCE_REPOSITORY_URL`
- `SKILLHUB_SOURCE_REF_TYPE`
- optional `SKILLHUB_SOURCE_REF`
- `SKILLHUB_DEV_GITLAB_REPOSITORY_URL`
- `SKILLHUB_DEV_GITLAB_BRANCH`
- `SKILLHUB_SOURCE_SCAN_STATUS`
- optional `SKILLHUB_SOURCE_SCAN_ID`
- trusted importer identity variables when available

The scan status must be exactly `PASSED`. The `pull_code` job is the trust gate:
it must not land a project or emit the artifact until the scan succeeds. The
target branch must be protected and writable only by that controlled landing
flow so content cannot change between landing and the publish job checkout.
Concurrent pipelines for the same target branch must serialize the complete
`pull_code` through `publish_skillhub` window, or each pipeline must use an
immutable pipeline-specific branch. Serializing only one of the two jobs does
not prevent a later landing from being fetched by an earlier publish job.
The landing flow must preserve the upstream Git commit object and hash. SkillHub
uses the derived Dev checkout revision with the original GitHub repository URL
for its provenance browse link; re-committing the files would make that link
invalid even though the imported package contents remain usable.

The `pull-code.env` artifact file is authoritative. GitLab exports dotenv values
into the later job, but pipeline, project, group, and instance variables can
override them. The importer therefore reads the file inside `CI_PROJECT_DIR`
and rejects missing files, unknown or duplicate keys, out-of-tree paths, and
any conflicting inherited handoff variable.

The Dev GitLab URL is credential-free HTTPS. `CI_JOB_TOKEN` is supplied separately
by GitLab and used only through Git subprocess environment configuration. It
must not appear in command arguments, artifacts, reports, errors, or SkillHub
requests. HTTP and Git redirects are disabled. The Dev project must allow the
central pipeline project to read it.

## Checkout identity and version fallback

Commit SHAs are not handoff variables. The importer fetches the configured Dev
GitLab branch, checks out `FETCH_HEAD`, and derives the resulting commit with
`git rev-parse HEAD`. That derived value is used only for the existing SkillHub
source-provenance API and report; operators and upstream jobs do not provide it.

The importer does not synthesize a commit-based version. If `SKILL.md` omits
`version`, the source-import workflow uses the same UTC `YYYYMMDDHHMMSS`
timestamp fallback as the normal publish workflow. An explicit `SKILL.md`
version remains authoritative.

## Preserved SkillHub behavior

No endpoint, schema, authorization, ownership, review, or scanner contract
changes are required. The source-import workflow is aligned with the existing
publish timestamp fallback, and the importer still calls:

- `PUT /api/cli/v1/source-imports/namespaces/{namespaceSlug}`
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills/validate`
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills`

The endpoints require an `st_` service token with `source:import`. All packages
are validated before any package is submitted. Submitted versions remain
`PENDING_REVIEW`; existing scanner and namespace-owner approval are not bypassed.
Idempotent retry outcomes and immutable explicit-version conflicts remain
unchanged.

## GitLab job interface

The shared template defines `skillhub_oss_import` in the `publish_skillhub`
stage and declares a hard `needs` edge to `pull_code` with artifacts enabled.
The central pipeline must list `publish_skillhub` after `pull_code` and must not
mark the intake gate as allowed to fail.

Required project/group variables remain:

- `SKILLHUB_PYTHON_IMAGE`
- `SKILLHUB_BASE_URL`
- `SKILLHUB_SERVICE_TOKEN`
- `SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE`
- `SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME`

`CI_PROJECT_DIR`, `CI_JOB_TOKEN`, `CI_PIPELINE_ID`, and `CI_JOB_ID` are supplied
by GitLab. The central repository's own commit and repository coordinates are
intentionally ignored by the importer.

## Verification contract

- Config tests reject missing Dev/upstream/scan handoff values, non-passed scans,
  unsafe source roots, invalid branches and refs, and old central checkout
  fallback behavior. They also reject all former SHA handoff keys.
- Checkout tests prove the requested Dev branch is fetched, the checked-out SHA
  is derived locally, no token appears in command arguments, errors remain
  credential-safe, and checkouts remain isolated.
- Runtime tests execute `run_import.py --help` with `python -S`, proving no
  site-packages are required, including under Python 3.8.
- HTTP tests use a real loopback server for subpath, JSON, multipart,
  authorization, request ID, and non-JSON failure behavior.
- The real-service smoke mounts the central pipeline checkout and Dev source as
  separate read-only paths, then exercises PostgreSQL, Redis, MinIO, scanner,
  backend, root proxy, and `/skillhub` proxy using the branch handoff.

## Non-goals

- No external GitHub credentials or direct external clone in the publish job.
- No shared job filesystem dependency.
- No TypeScript SkillHub CLI or OAuth Device Flow.
- No direct publication, scanner bypass, review bypass, owner transfer, or
  deletion of skills absent from a later source revision.

# OSS GitHub Source Import GitLab Implementation Plan

> **2026-08-24 correction:** Runner-side tasks that assume an existing OSS checkout, a
> dedicated importer image, or an installed `skillhub-oss-import` command are superseded
> by `2026-08-24-oss-import-central-project-python-runner.md`. The GitHub repository is
> already present in the internal GitLab source project. Its checked-in shell calls
> Python, which clones `CI_REPOSITORY_URL` at `CI_COMMIT_SHA`; the supplied GitHub URL is
> only upstream identity/provenance. Backend/API and governance tasks in this historical
> plan remain applicable.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Python 3.12 GitLab Runner job that imports every checked-out GitHub skill into SkillHub through idempotent, bearer-authenticated source-import APIs while preserving scanner and namespace-owner review.

**Architecture:** A standalone Python importer owns checkout validation, discovery, deterministic ZIP construction, all-package preflight, sequential submission, and reporting. A focused FastAPI source-import module owns identity, namespace binding, idempotency, provenance, and composition of existing publish workflows. Local PostgreSQL extension tables preserve the upstream-followed core schema, and existing review/skill read models expose provenance without weakening visibility rules.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, PostgreSQL, Redis, S3/MinIO, pytest, httpx, React, TypeScript, TanStack Query, Vitest, Docker Compose, Nginx, GitLab CI YAML.

---

## Governing decisions

Implement against the approved design in
`docs/backend-python-maintenance/plans/2026-08-18-oss-github-source-import-gitlab-design.md`.
The following constraints are acceptance requirements, not optional refinements:

- Keep FastAPI routes root-relative. `/skillhub` is added and stripped by the public proxy.
- Accept only canonicalizable `https://github.com/<owner>/<repo>[.git]` sources.
- Never clone or fetch source repositories from the backend.
- Never auto-publish an OSS import, including for a `SUPER_ADMIN` importer actor.
- Require a bearer API token with `source:import` and actor role `SKILL_ADMIN` or `SUPER_ADMIN`.
- Keep `source:import` out of ordinary token defaults.
- Resolve people by `identity_binding(provider_code, login_name)`; `CLIENT_NAME=tsso` is not an identity key.
- Keep importer actor, review submitter, and stable skill owner distinct.
- Preserve existing skill ownership on later imports.
- Store organization-specific provenance in Python-owned local tables.
- Validate every discovered package before submitting any of them.
- Run the final verification with PostgreSQL, Redis, MinIO, scanner, backend, web, and the public proxy, for both `/` and `/skillhub` routing.

## Task 1: Add the local provenance schema

**Files:**

- Create: `server-python/app/db/local_migration/20260818_01__oss_source_import.sql`
- Modify: `server-python/tests/test_schema_migration_baseline.py`
- Create: `server-python/tests/test_oss_source_schema_postgres.py`

- [ ] Write a failing migration registry test asserting identifier `20260818_01`, the three table names, required unique constraints, and foreign-key deletion behavior are present.
- [ ] Write a PostgreSQL integration test that applies migrations, inserts a namespace/skill/version fixture and all three provenance rows, proves duplicate repository URL, duplicate namespace binding, duplicate source path, and duplicate version provenance are rejected, then proves version provenance cascades when the skill version is deleted.
- [ ] Run the focused tests and confirm the new assertions fail before adding SQL:

```powershell
cd server-python
uv run --no-cache pytest tests/test_schema_migration_baseline.py tests/test_oss_source_schema_postgres.py -q
```

Expected before implementation: failures for the missing migration/tables.

- [ ] Add the migration with this durable shape:

```sql
CREATE TABLE IF NOT EXISTS local_oss_namespace_source (
    id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL UNIQUE REFERENCES namespace(id) ON DELETE CASCADE,
    repository_url VARCHAR(500) NOT NULL UNIQUE,
    created_by VARCHAR(255) NOT NULL REFERENCES user_account(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS local_oss_skill_source (
    id BIGSERIAL PRIMARY KEY,
    namespace_source_id BIGINT NOT NULL REFERENCES local_oss_namespace_source(id) ON DELETE CASCADE,
    source_path VARCHAR(1000) NOT NULL,
    skill_id BIGINT NOT NULL UNIQUE REFERENCES skill(id) ON DELETE CASCADE,
    created_by VARCHAR(255) NOT NULL REFERENCES user_account(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (namespace_source_id, source_path)
);

CREATE TABLE IF NOT EXISTS local_oss_skill_version_source (
    id BIGSERIAL PRIMARY KEY,
    skill_source_id BIGINT NOT NULL REFERENCES local_oss_skill_source(id) ON DELETE CASCADE,
    skill_version_id BIGINT NOT NULL UNIQUE REFERENCES skill_version(id) ON DELETE CASCADE,
    repository_revision_sha CHAR(40) NOT NULL,
    source_ref_type VARCHAR(16) NOT NULL CHECK (source_ref_type IN ('TAG', 'BRANCH', 'COMMIT')),
    source_ref VARCHAR(500),
    content_fingerprint CHAR(64) NOT NULL,
    imported_by VARCHAR(255) NOT NULL REFERENCES user_account(id),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (skill_source_id, content_fingerprint)
);
```

- [ ] Add explicit indexes only where the uniqueness constraints do not already provide them and query plans require them; do not add columns to core Flyway tables.
- [ ] Run the focused tests again and expect all to pass.
- [ ] Commit:

```powershell
git add server-python/app/db/local_migration/20260818_01__oss_source_import.sql server-python/tests/test_schema_migration_baseline.py server-python/tests/test_oss_source_schema_postgres.py
git commit -m "feat(import): add OSS source provenance schema"
```

## Task 2: Build canonical source contracts and fingerprinting

**Files:**

- Create: `server-python/app/source_import/__init__.py`
- Create: `server-python/app/source_import/contracts.py`
- Create: `server-python/app/source_import/source.py`
- Create: `server-python/tests/test_source_import_source.py`

- [ ] Write parameterized tests for accepted URLs, rejected schemes/hosts/ports/credentials/query/fragment/path depth, namespace slug/display derivation, source-path normalization, SHA validation, and commit browse URL encoding.
- [ ] Write a deterministic fingerprint test proving archive order and ZIP metadata do not affect the result while any path or file byte change does.
- [ ] Run and observe the missing-module failure:

```powershell
cd server-python
uv run --no-cache pytest tests/test_source_import_source.py -q
```

- [ ] Implement typed immutable contracts for `SourceRepository`, `SourceRevision`, `SourceIdentity`, `SourcePackage`, `SourceProvenance`, and outcome literals.
- [ ] Implement strict URL canonicalization with `urllib.parse`, source-path POSIX normalization, and a backend-authoritative digest over sorted normalized entries:

```python
def content_fingerprint(entries: list[PackageEntry]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item.path):
        file_digest = hashlib.sha256(entry.content).hexdigest()
        digest.update(entry.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
```

- [ ] Ensure browse links use only the canonical repository URL, validated 40-character commit SHA, and percent-encoded normalized source path.
- [ ] Run the focused tests and commit:

```powershell
uv run --no-cache pytest tests/test_source_import_source.py -q
cd ..
git add server-python/app/source_import server-python/tests/test_source_import_source.py
git commit -m "feat(import): define OSS source contracts"
```

## Task 3: Implement identity and namespace provisioning

**Files:**

- Create: `server-python/app/source_import/repository.py`
- Create: `server-python/app/source_import/service.py`
- Create: `server-python/tests/test_source_import_namespace.py`
- Create: `server-python/tests/test_source_import_namespace_postgres.py`

- [ ] Write repository/service tests for exact case-sensitive `provider_code + login_name` lookup, missing binding, duplicate binding, disabled account, one current owner, missing/multiple current owners, existing repository binding, slug collision, repository collision, invalid namespace type/status, and creation.
- [ ] Write a real PostgreSQL test proving namespace creation, OWNER membership, repository binding, and audit record commit in one transaction, and proving a forced binding failure rolls the whole operation back.
- [ ] Run focused tests and confirm they fail before implementation.
- [ ] Implement a repository with SQL-only persistence and typed rows. Keep all SQL out of the API route.
- [ ] Implement the ensure workflow so a missing namespace uses the configured fallback identity, creates an `ACTIVE` `TEAM` namespace, adds that user as `OWNER`, binds the canonical repository, and writes an audit entry whose actor is the API-token principal.
- [ ] For an existing valid binding, return the current namespace owner without changing display name, owner, membership, or state.
- [ ] Treat zero or multiple active owners as corrupted governance and return a conflict rather than choosing one.
- [ ] Add attribution resolution that returns an active unique initiator when supplied, falls back only for absent/not-found identities, and fails for ambiguous or disabled identities.
- [ ] Run focused tests and commit:

```powershell
cd server-python
uv run --no-cache pytest tests/test_source_import_namespace.py tests/test_source_import_namespace_postgres.py -q
cd ..
git add server-python/app/source_import server-python/tests/test_source_import_namespace.py server-python/tests/test_source_import_namespace_postgres.py
git commit -m "feat(import): provision repository namespaces"
```

## Task 4: Separate publish owner, submitter, and actor

**Files:**

- Modify: `server-python/app/publish/orchestration.py`
- Modify: `server-python/app/publish/transaction.py`
- Modify: `server-python/app/publish/side_effects.py`
- Modify: `server-python/tests/test_publish_orchestration.py`
- Modify: `server-python/tests/test_publish_transaction.py`
- Modify: `server-python/tests/test_publish_side_effects.py`
- Modify: `server-python/tests/test_publish_review_download_session_flow.py`

- [ ] Add failing tests proving `owner_id` controls skill ownership/version creator, `submitter_id` controls `review_task.submitted_by` and review notifications/events, and `actor_user_id` controls audit attribution and replacement archive actions.
- [ ] Add regression tests proving omitted fields keep all existing publish routes equivalent to the current single-publisher behavior.
- [ ] Extend `PublishWriteInput` without forcing callers to duplicate identifiers:

```python
@dataclass(frozen=True)
class PublishWriteInput:
    # existing fields remain
    publisher_id: str
    submitter_id: str | None = None
    actor_user_id: str | None = None

    @property
    def resolved_submitter_id(self) -> str:
        return self.submitter_id or self.publisher_id

    @property
    def resolved_actor_user_id(self) -> str:
        return self.actor_user_id or self.publisher_id
```

- [ ] Pass stable owner/publisher into core skill/version writes, resolved submitter into review task/notification creation, and resolved actor into audit/archive operations. Do not rename the existing public publish contract.
- [ ] Keep scanner payload publisher semantics tied to the stable skill owner unless an existing consumer contract explicitly requires submitter; record the chosen behavior in its test.
- [ ] Run all publish tests, not only the edited files:

```powershell
cd server-python
uv run --no-cache pytest tests/test_publish*.py -q
```

- [ ] Commit:

```powershell
cd ..
git add server-python/app/publish server-python/tests/test_publish_orchestration.py server-python/tests/test_publish_transaction.py server-python/tests/test_publish_side_effects.py server-python/tests/test_publish_review_download_session_flow.py
git commit -m "refactor(publish): separate import identities"
```

## Task 5: Implement idempotent source-package validation

**Files:**

- Modify: `server-python/app/source_import/contracts.py`
- Modify: `server-python/app/source_import/repository.py`
- Modify: `server-python/app/source_import/service.py`
- Create: `server-python/tests/test_source_import_validation.py`
- Create: `server-python/tests/test_source_import_validation_postgres.py`

- [ ] Write tests for unchanged source path/fingerprint, already-imported version/fingerprint, source-path slug drift, explicit-version content conflict, missing-version override, illegal override with explicit source version, existing stable owner, new effective owner, non-member attribution plan, and forced `PUBLIC`/non-auto-publish behavior.
- [ ] Exercise these rules with a real PostgreSQL fixture containing accepted, pending, rejected, and published versions.
- [ ] Reuse `extract_package`, `validate_package`, `PublishDryRunRepository`, and metadata parsing instead of introducing a second package validator.
- [ ] Resolve the effective version in this order:

```python
if metadata.version:
    reject_nonempty_override()
    effective_version = metadata.version
else:
    effective_version = require_valid_version_override()
```

- [ ] Resolve by repository binding plus source path before slug. If the binding exists, require its skill slug to equal the package-resolved slug and preserve its `owner_id`.
- [ ] Return a typed plan with exactly `IMPORT`, `SKIPPED_UNCHANGED`, or `SKIPPED_ALREADY_IMPORTED`. Return conflicts for source identity drift or immutable explicit-version mismatch.
- [ ] Keep validation read-only: no membership, audit, storage, skill, version, or provenance writes.
- [ ] Run focused tests and commit:

```powershell
cd server-python
uv run --no-cache pytest tests/test_source_import_validation.py tests/test_source_import_validation_postgres.py -q
cd ..
git add server-python/app/source_import server-python/tests/test_source_import_validation.py server-python/tests/test_source_import_validation_postgres.py
git commit -m "feat(import): validate idempotent source packages"
```

## Task 6: Compose transactional submission with publish and provenance

**Files:**

- Modify: `server-python/app/source_import/service.py`
- Modify: `server-python/app/source_import/repository.py`
- Modify: `server-python/app/publish/orchestration.py`
- Create: `server-python/tests/test_source_import_submission.py`
- Create: `server-python/tests/test_source_import_submission_postgres.py`

- [ ] Write failing unit tests for new-source import, later-version import by another trigger, namespace MEMBER insertion, actor/submitter/owner separation, scanner handoff, review creation, and every skip/conflict outcome.
- [ ] Write a real PostgreSQL transaction test proving `skill`, `skill_version`, membership, source binding, version provenance, review task, security audit, and audit log are mutually consistent after commit and absent after an injected failure.
- [ ] Extend `execute_publish_write` with a transaction-scoped `before_publish` or focused callback only if needed to insert namespace membership and source binding in the same DB transaction. Keep storage compensation behavior intact.
- [ ] Persist `local_oss_skill_source` immediately after the new skill ID exists and persist `local_oss_skill_version_source` after the new version ID exists, using the backend-computed fingerprint and actor identity.
- [ ] Force the source-import request to `visibility="PUBLIC"` and `auto_publish=False`, independent of platform role.
- [ ] Pass stable owner as `publisher_id`, attribution user as `submitter_id`, and API token principal as `actor_user_id`.
- [ ] Add a dedicated `SOURCE_IMPORT_SKILL_VERSION` audit detail containing canonical repository, commit SHA, ref type/ref, source path, outcome, stable owner, and review submitter; never include the raw token.
- [ ] Ensure uniqueness races map to deterministic skip/conflict responses by rereading persisted state after `IntegrityError`, not by returning HTTP 500.
- [ ] Run focused plus publish suites and commit:

```powershell
cd server-python
uv run --no-cache pytest tests/test_source_import_submission.py tests/test_source_import_submission_postgres.py tests/test_publish*.py -q
cd ..
git add server-python/app/source_import server-python/app/publish/orchestration.py server-python/tests/test_source_import_submission.py server-python/tests/test_source_import_submission_postgres.py
git commit -m "feat(import): submit source packages for review"
```

## Task 7: Add the authenticated source-import API

**Files:**

- Create: `server-python/app/api/source_imports.py`
- Modify: `server-python/app/main.py`
- Create: `server-python/scripts/export_source_import_openapi.py`
- Create: `server-python/tests/test_source_import_api.py`
- Create: `server-python/tests/test_source_import_openapi.py`

- [ ] Write route tests for bearer-only access, missing/wrong scope, missing platform role, mock/session principal rejection, malformed JSON form metadata, invalid ZIP, namespace path/body mismatch, success envelopes, skips, conflicts, and request IDs.
- [ ] Write an OpenAPI contract test for the ensure, validate, and submit paths and their typed request/response bodies.
- [ ] Resolve auth with `resolve_current_user_or_401`, then require all three conditions explicitly:

```python
if not is_api_token_principal(user):
    raise HTTPException(status_code=403, detail="error.sourceImport.apiToken.required")
require_api_token_scope(user, "source:import")
require_any_platform_role(
    user,
    {"SKILL_ADMIN", "SUPER_ADMIN"},
    detail="error.sourceImport.platformRole.required",
)
```

- [ ] Implement exactly these root-relative routes:

```text
PUT  /api/cli/v1/source-imports/namespaces/{namespaceSlug}
POST /api/cli/v1/source-imports/{namespaceSlug}/skills/validate
POST /api/cli/v1/source-imports/{namespaceSlug}/skills
```

- [ ] Model the ensure body exactly as `repositoryUrl`, `displayName`, `fallbackOwnerProviderCode`, and `fallbackOwnerLoginName`; reject a path/body-derived namespace mismatch.
- [ ] Accept one ZIP `file` plus one JSON `metadata` form field for skill calls. The metadata fields are `repositoryUrl`, `repositoryRevisionSha`, `sourceRefType`, optional `sourceRef`, `sourcePath`, optional `versionOverride`, optional `initiatorProviderCode`, optional `initiatorLoginName`, optional `pipelineId`, optional `jobId`, and optional `ciRefName`. Model them with Pydantic `extra="forbid"`; do not accept a caller-supplied content fingerprint or browse URL.
- [ ] Return typed ensure data with `CREATED|EXISTING`; typed validation data with the planned outcome/effective coordinate/version/owner/submitter/provenance; and typed submit data with `IMPORTED|SKIPPED_UNCHANGED|SKIPPED_ALREADY_IMPORTED`, status, optional review task, actor, owner, submitter, and provenance.
- [ ] Register the router in `app/main.py` and keep SQL/workflow logic outside the route.
- [ ] Export a focused OpenAPI document for the standalone importer client and verify stable generation.
- [ ] Run route, policy, and OpenAPI tests and commit:

```powershell
cd server-python
uv run --no-cache pytest tests/test_source_import_api.py tests/test_source_import_openapi.py tests/test_route_policy_enforcement.py -q
cd ..
git add server-python/app/api/source_imports.py server-python/app/main.py server-python/scripts/export_source_import_openapi.py server-python/tests/test_source_import_api.py server-python/tests/test_source_import_openapi.py
git commit -m "feat(api): expose OSS source import endpoints"
```

## Task 8: Expose provenance in protected review reads and published version reads

**Files:**

- Modify: `server-python/app/review/query.py`
- Modify: `server-python/app/skills/read_repository.py`
- Modify: `server-python/app/skills/read_responses.py`
- Modify: `server-python/app/api/reviews.py`
- Modify: `server-python/tests/test_review_detail.py`
- Modify: `server-python/tests/test_review_skill_detail.py`
- Modify: `server-python/tests/test_skill_version_detail.py`
- Modify: `server-python/tests/test_skill_version_detail_repository.py`
- Modify: `server-python/tests/test_source_import_openapi.py`

- [ ] Write tests proving review detail includes provenance for its exact pending/rejected version, published version detail includes provenance for its exact version, non-imported versions return `sourceProvenance: null`, and public reads cannot select pending/rejected provenance.
- [ ] Add one shared response builder that returns:

```json
{
  "repositoryUrl": "https://github.com/mattpocock/skills",
  "repositoryRevisionSha": "0123456789abcdef0123456789abcdef01234567",
  "sourceRefType": "BRANCH",
  "sourceRef": "main",
  "sourcePath": "skills/engineering/code-review",
  "contentFingerprint": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "browseUrl": "https://github.com/mattpocock/skills/tree/0123456789abcdef0123456789abcdef01234567/skills/engineering/code-review"
}
```

- [ ] Join provenance by exact `skill_version_id`, never by latest source row.
- [ ] Preserve current review authorization before returning protected provenance.
- [ ] Preserve current published/owner-preview resolution rules; anonymous callers must not receive provenance for a non-published version.
- [ ] Run focused tests and commit:

```powershell
cd server-python
uv run --no-cache pytest tests/test_review_detail.py tests/test_review_skill_detail.py tests/test_skill_version_detail.py tests/test_skill_version_detail_repository.py tests/test_source_import_openapi.py -q
cd ..
git add server-python/app/review/query.py server-python/app/skills server-python/app/api/reviews.py server-python/tests/test_review_detail.py server-python/tests/test_review_skill_detail.py server-python/tests/test_skill_version_detail.py server-python/tests/test_skill_version_detail_repository.py server-python/tests/test_source_import_openapi.py
git commit -m "feat(import): expose source provenance reads"
```

## Task 9: Display provenance in review and skill-version UI

**Files:**

- Modify: `web/src/api/types.ts`
- Modify: `web/src/features/review/review-skill-detail-section.tsx`
- Modify: `web/src/features/review/review-skill-detail-section.test.tsx`
- Create: `web/src/features/skill/source-provenance.tsx`
- Create: `web/src/features/skill/source-provenance.test.tsx`
- Modify: `web/src/pages/skill-detail.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/package.json`
- Generate: `web/src/api/generated/source-import-openapi.json`
- Generate: `web/src/api/generated/source-import-schema.d.ts`

- [ ] Add component tests for repository, tag/branch label, abbreviated commit, source path, safe exact-commit link, missing provenance, and keyboard-accessible external-link behavior.
- [ ] Generate focused types through a new `generate-api:source-import` script; do not hand-edit generated files.
- [ ] Define the reusable `SourceProvenance` TypeScript type from the generated schema and add it to review skill detail and version detail contracts.
- [ ] Render a compact provenance card in the expanded review detail and the selected version detail. Do not show a card for ordinary SkillHub-native skills.
- [ ] Use translation keys in all three existing locale files; do not hardcode UI copy.
- [ ] Use an ordinary HTTPS anchor with `target="_blank"` and `rel="noreferrer"`; do not build links from `window.location`, so `/skillhub` does not affect GitHub links.
- [ ] Run focused frontend checks:

```powershell
cd web
pnpm run generate-api:source-import
pnpm exec vitest run src/features/review/review-skill-detail-section.test.tsx src/features/skill/source-provenance.test.tsx
pnpm run typecheck
pnpm run lint
```

- [ ] Commit:

```powershell
cd ..
git add web/package.json web/src/api web/src/features/review web/src/features/skill/source-provenance.tsx web/src/features/skill/source-provenance.test.tsx web/src/pages/skill-detail.tsx web/src/i18n/locales
git commit -m "feat(web): show OSS source provenance"
```

## Task 10: Create the standalone Python importer

**Files:**

- Create: `tools/oss-source-importer/pyproject.toml`
- Generate: `tools/oss-source-importer/uv.lock`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/__init__.py`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/config.py`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/github_source.py`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/discovery.py`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/package.py`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/client.py`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/orchestrator.py`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/report.py`
- Create: `tools/oss-source-importer/src/skillhub_oss_importer/cli.py`
- Create: `tools/oss-source-importer/tests/test_config.py`
- Create: `tools/oss-source-importer/tests/test_github_source.py`
- Create: `tools/oss-source-importer/tests/test_discovery.py`
- Create: `tools/oss-source-importer/tests/test_package.py`
- Create: `tools/oss-source-importer/tests/test_client.py`
- Create: `tools/oss-source-importer/tests/test_orchestrator.py`
- Create: `tools/oss-source-importer/tests/test_cli.py`

- [ ] Start with tests for the exact environment-variable contract, public base URL normalization including `/skillhub`, strict GitHub URL/naming, `git rev-parse HEAD` equality, tag/branch/commit ref selection, exit-code mapping, redaction, and atomic report writing.
- [ ] Add discovery tests using real temporary directories: exact-case `SKILL.md`, `.git` exclusion, no symlink following, containment, sorted roots, no-skill failure, and safe source-root subdirectory.
- [ ] Add deterministic ZIP tests proving `SKILL.md` is at ZIP root, nested skill roots are excluded from ancestors, source bytes are unchanged, archive paths/timestamps/permissions are stable, and the same checkout produces identical bytes.
- [ ] Add fake-http tests proving ensure once, validate all before any submit, zero submits on any validation failure, sequential submits, continue-after-submit-error, idempotent skip handling, timeouts, request ID logging, and token redaction.
- [ ] Assert and implement the exact importer variable contract: required `SKILLHUB_BASE_URL`, `SKILLHUB_API_TOKEN`, `SKILLHUB_SOURCE_REPOSITORY_URL`, and `SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME`; optional `SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE` (defaults to `keycloak`), `SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME`, `SKILLHUB_IMPORT_SOURCE_ROOT`, `SKILLHUB_IMPORT_REPORT_PATH`, `SKILLHUB_IMPORT_TIMEOUT_SECONDS`, and `SSL_CERT_FILE`; GitLab context `CI_PROJECT_DIR`, `CI_COMMIT_SHA`, `CI_COMMIT_TAG`, `CI_COMMIT_BRANCH`, `CI_COMMIT_REF_NAME`, `CI_PIPELINE_ID`, and `CI_JOB_ID`. The CI template, not the Python config, additionally requires `SKILLHUB_IMPORTER_IMAGE`.
- [ ] Use a packaged console script and pinned compatible dependencies:

```toml
[project]
name = "skillhub-oss-source-importer"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["httpx>=0.28,<1"]

[project.scripts]
skillhub-oss-import = "skillhub_oss_importer.cli:main"

[dependency-groups]
dev = ["pytest>=8,<9", "ruff>=0.12,<1"]
```

- [ ] `Config.from_env()` must require all documented variables, default trigger provider from owner provider, keep trigger login optional, validate source root is within `CI_PROJECT_DIR`, and never include the token in dataclass repr/errors/report.
- [ ] Verify `CI_COMMIT_SHA` is lowercase-normalized 40-hex and equals `git -C <root> rev-parse HEAD` before calling SkillHub.
- [ ] Send the ZIP bytes as multipart `file` and JSON as multipart `metadata`, using `${SKILLHUB_BASE_URL}/api/cli/v1/...` without stripping a valid `/skillhub` prefix.
- [ ] Define stable exits: `0` success/all skipped, `2` configuration, `3` discovery/package/validation, `4` authorization, `5` transport, `6` partial submission, `10` unexpected internal failure.
- [ ] Write the JSON report through a temporary sibling and `Path.replace`, including repository, commit/ref, namespace, pipeline/job IDs, per-path validation/submission outcome, coordinate/version/review task, request ID, and final status.
- [ ] Run importer tests, lint, build, and help:

```powershell
cd tools/oss-source-importer
uv lock
uv sync --frozen
uv run --no-cache pytest -q
uv run --no-cache ruff check .
uv build
uv run skillhub-oss-import --help
```

- [ ] Commit:

```powershell
cd ../..
git add tools/oss-source-importer
git commit -m "feat(importer): package GitLab OSS import client"
```

## Task 11: Add importer image and reusable GitLab stage

**Files:**

- Create: `tools/oss-source-importer/Dockerfile`
- Create: `deploy/gitlab/oss-source-import.yml`
- Create: `tools/oss-source-importer/tests/test_gitlab_template.py`
- Modify: `.dockerignore` if the repository has one and the build context requires it

- [ ] Test the YAML/text contract for pinned importer image variable use, no inline script installation, required variable forwarding, JSON report artifact with `when: always`, and a single console command.
- [ ] Build a non-root Python 3.12 image with only the locked runtime environment, Git executable needed for revision verification, CA certificate support, console entry point, and no source-repository clone logic.
- [ ] Create a reusable hidden job plus an example stage:

```yaml
.skillhub_oss_import:
  image: "$SKILLHUB_IMPORTER_IMAGE"
  script:
    - skillhub-oss-import --json-report "$SKILLHUB_IMPORT_REPORT_PATH"
  artifacts:
    when: always
    paths:
      - "$SKILLHUB_IMPORT_REPORT_PATH"

skillhub_oss_import:
  extends: .skillhub_oss_import
  stage: publish
```

- [ ] Do not use `latest`, `curl | sh`, the TypeScript CLI, Docker-in-Docker, or a long-running K8s importer workload.
- [ ] Validate tests and image:

```powershell
cd tools/oss-source-importer
uv run --no-cache pytest tests/test_gitlab_template.py -q
cd ../..
docker build -t skillhub-oss-source-importer:verify -f tools/oss-source-importer/Dockerfile tools/oss-source-importer
docker run --rm skillhub-oss-source-importer:verify --help
```

- [ ] Commit:

```powershell
git add tools/oss-source-importer/Dockerfile tools/oss-source-importer/tests/test_gitlab_template.py deploy/gitlab/oss-source-import.yml .dockerignore
git commit -m "build(importer): add GitLab import stage image"
```

If `.dockerignore` does not exist or does not need modification, omit it from `git add` rather than creating an unrelated file.

## Task 12: Write the Traditional Chinese deployment and usage SOP

**Files:**

- Create: `deploy/k8s/oss-github-source-import.zh.md`
- Modify: `deploy/k8s/README.md`
- Modify: `deploy/k8s/environment-variables.zh.md`
- Modify: `README_zh.md`
- Create: `server-python/tests/test_oss_source_import_docs.py`

- [ ] Write a doc contract test asserting every required/optional variable, exact endpoints, `keycloak` versus `tsso`, `/skillhub` base URL example, token scope/role, import status semantics, review steps, report artifact, retry behavior, and troubleshooting sections appear.
- [ ] Document how a platform admin creates or provisions a dedicated service-account token with `source:import`; explicitly warn that the ordinary token UI/default `skill:read` and `skill:publish` scopes do not add this scope. Do not require those ordinary scopes for the three source-import endpoints unless the same token is intentionally used for separate APIs.
- [ ] Provide a copy-ready GitLab include/job example that maps the organization’s preferred-username variable into `SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME` without claiming that GitLab always provides a Keycloak preferred username.
- [ ] Document all exact variables from the approved spec, marking `SKILLHUB_API_TOKEN` masked/protected and `SKILLHUB_IMPORTER_IMAGE` immutable by version/digest.
- [ ] Explain that pipeline success means imported/skipped and pending scanner/review, not published; show the namespace owner’s existing review route and provenance evidence.
- [ ] Include operator checks for identity not found, disabled/ambiguous identity, namespace/source collision, explicit-version conflict, zero `SKILL.md`, commit mismatch, certificate errors, partial submissions, and report/request-ID correlation.
- [ ] Link the SOP from K8s and Chinese root docs, then run:

```powershell
cd server-python
uv run --no-cache pytest tests/test_oss_source_import_docs.py -q
```

- [ ] Commit:

```powershell
cd ..
git add deploy/k8s/oss-github-source-import.zh.md deploy/k8s/README.md deploy/k8s/environment-variables.zh.md README_zh.md server-python/tests/test_oss_source_import_docs.py
git commit -m "docs(import): add GitLab import SOP"
```

## Task 13: Add real full-stack source-import smoke coverage

**Files:**

- Create: `scripts/oss-source-import-smoke-test.ps1`
- Create: `docker-compose.oss-source-import-test.yml`
- Create: `tests/fixtures/oss-source-repository/skills/alpha/SKILL.md`
- Create: `tests/fixtures/oss-source-repository/skills/alpha/reference.md`
- Create: `tests/fixtures/oss-source-repository/skills/parent/SKILL.md`
- Create: `tests/fixtures/oss-source-repository/skills/parent/nested/SKILL.md`
- Create: `tests/fixtures/oss-source-repository/skills/parent/nested/example.txt`
- Modify: `web/e2e/subpath-deployment.spec.ts`
- Modify: `docs/backend-python-maintenance/verification.md` if this repository uses it for current evidence; otherwise create `docs/backend-python-maintenance/oss-source-import-verification.md`

- [ ] Add a test-only Compose overlay that starts MinIO, configures the `server` service with `SKILLHUB_STORAGE_PROVIDER=s3`, points it at that MinIO service, auto-creates an isolated bucket, and enables the real Redis scan consumer. Do not change release defaults or add MinIO as a production K8s workload.
- [ ] Have the smoke script copy the committed fixture tree into a uniquely named temporary directory, initialize a local Git repository, create deterministic commits, and expose that directory as `CI_PROJECT_DIR`; never modify the tracked fixture while testing changed revisions.
- [ ] Make the smoke script create uniquely named database users/identities/token/source fixture state through PostgreSQL setup SQL, run the real migration command, and clean only its own uniquely prefixed records in `finally`.
- [ ] Run the built importer image against the fixture checkout through the public Nginx address, not directly against uvicorn.
- [ ] Verify the first import creates the namespace and all skills, database rows use the expected actor/submitter/owner, MinIO contains package objects, Redis/scanner advances the scan, namespace review sees provenance, and no imported version is auto-published.
- [ ] Approve one review through the normal API, then verify public skill/version detail exposes the exact commit provenance and browse URL.
- [ ] Run the same import again and assert only skip outcomes and no duplicate versions/storage/source rows.
- [ ] Change one unversioned fixture skill, commit it in the fixture repository, rerun with the new SHA, and assert only that source path receives a new deterministic `git-` plus 40-character SHA version.
- [ ] Add a `/skillhub` deployment case to the existing subpath E2E/smoke coverage. The importer must call `/skillhub/api/cli/...`; the proxy must strip the base and the backend must still see `/api/cli/...`.
- [ ] Record exact commands, timestamps, image tags, request IDs, and observed outcomes in the verification doc. Do not claim success from unit tests alone.

Use this verification sequence, adapting only explicit port variables to avoid collisions:

```powershell
docker compose --env-file .env.release.example -f compose.release.yml -f docker-compose.oss-source-import-test.yml up -d --build postgres redis minio skill-scanner server web
cd server-python
uv run --no-cache python -m app.migrations upgrade
cd ..
powershell -ExecutionPolicy Bypass -File scripts/oss-source-import-smoke-test.ps1
cd web
pnpm exec playwright test e2e/subpath-deployment.spec.ts
cd ..
docker compose --env-file .env.release.example -f compose.release.yml -f docker-compose.oss-source-import-test.yml ps
docker compose --env-file .env.release.example -f compose.release.yml -f docker-compose.oss-source-import-test.yml logs --no-color postgres redis minio skill-scanner server web
```

Expected: every listed service is healthy/running, migrations are current, importer returns success, review/provenance assertions pass, retry is idempotent, `/skillhub` works, and logs contain no unhandled traceback, SQL syntax error, or repeated scanner failure for the test versions.

- [ ] Commit smoke fixtures, script, E2E change, and fresh evidence only after the complete environment passes:

```powershell
git add scripts/oss-source-import-smoke-test.ps1 docker-compose.oss-source-import-test.yml tests/fixtures/oss-source-repository web/e2e/subpath-deployment.spec.ts docs/backend-python-maintenance
git commit -m "test(import): verify full OSS import workflow"
```

## Task 14: Run release-quality verification and review the branch

**Files:**

- Modify only files required to fix failures found by these checks.

- [ ] Run all backend tests against the configured PostgreSQL integration environment:

```powershell
cd server-python
uv sync --frozen
uv run --no-cache pytest tests -q
```

- [ ] Run all importer checks:

```powershell
cd ..\tools\oss-source-importer
uv sync --frozen
uv run --no-cache pytest -q
uv run --no-cache ruff check .
uv build
```

- [ ] Run all frontend checks:

```powershell
cd ..\..\web
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run lint
pnpm test -- --run
pnpm run build
```

- [ ] Run deployment/build gates:

```powershell
cd ..
docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
docker build -t skillhub-oss-source-importer:verify -f tools/oss-source-importer/Dockerfile tools/oss-source-importer
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check origin/dev...HEAD
```

- [ ] Review `git diff --stat origin/dev...HEAD` and `git diff origin/dev...HEAD` against the approved design. Confirm no Java/Maven/Spring files, ordinary-token default scope change, auto-publish path, source fetching, ownership transfer, removed-skill deletion, or unrelated cleanup entered the branch.
- [ ] Run the full-stack smoke from Task 13 once more on the final commit and update the verification evidence with its exact final result.
- [ ] If verification produces fixes, commit each scoped fix with an imperative subject. End with a clean worktree:

```powershell
git status --short --branch
```

Expected: `codex/oss-source-import` is ahead of `origin/dev` only by the intended commits and has no uncommitted files.

## Final acceptance checklist

- [ ] `mattpocock/skills` derives `oss-mattpocock-skills` / `OSS-mattpocock-skills`.
- [ ] Every exact `SKILL.md` parent becomes one independent deterministic package.
- [ ] Nested roots are packaged independently without duplication.
- [ ] The GitLab checkout SHA is verified locally before any API mutation.
- [ ] Missing source version becomes `git-<40-char-sha>` without modifying `SKILL.md`.
- [ ] Namespace creation uses the configured Keycloak login and preserves later owner changes.
- [ ] Initiator lookup uses Keycloak `preferred_username` mapped to `login_name`; missing initiator falls back to the current namespace owner.
- [ ] Importer actor, review submitter, and stable skill owner are visible and correct.
- [ ] A different later pipeline initiator cannot transfer the existing skill owner.
- [ ] Validation mutates nothing and all packages validate before the first submission.
- [ ] Retry and unrelated-repository-commit cases return deterministic skip outcomes.
- [ ] Explicit-version content conflicts and source-path slug drift fail closed.
- [ ] Scanner and namespace-owner review remain mandatory; imported versions do not auto-publish.
- [ ] Review and published-version UIs show exact-commit provenance without leaking pending data publicly.
- [ ] Root and `/skillhub` public routes both work.
- [ ] PostgreSQL, Redis, MinIO, scanner, backend, and web/proxy were running during final verification.
- [ ] The Chinese SOP contains the exact deployment variables, token scope/role, pipeline example, review procedure, and troubleshooting guidance.
- [ ] No commit, push, merge, or PR is performed beyond the feature-branch commits unless the user explicitly authorizes it.

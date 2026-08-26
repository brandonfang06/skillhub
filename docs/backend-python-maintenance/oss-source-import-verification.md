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

Final result at 2026-08-18 16:48 +08:00, after recreating the services from
the committed branch images without caller-provided environment overrides:

```text
OSS source import smoke passed: run=e873baf36483 initial=de6c82530de2289f6b0a5459d2b44e4ad3f72bb8 changed=751d5b65985d61995c303d03ae896b965b51af63
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
9. committed a change to only the unversioned Alpha fixture, imported through `/skillhub`, and received exactly `git-751d5b65985d61995c303d03ae896b965b51af63` for Alpha while unchanged skills skipped;
10. proved the second trigger became the new review submitter without transferring the existing stable skill owner.

The final three-minute log window for PostgreSQL, Redis, MinIO, scanner,
backend, root web, and subpath web contained no traceback, scanner task failure,
SQL syntax error, unhandled exception, fatal, panic, or error entry.

The test overlay fixes its own PostgreSQL and Redis credentials and its
`55432`, `56379`, `58081`, `58080`, and `58082` host ports. The smoke script
asserts that resolved Compose contract before changing any database state, so
the verification cannot silently depend on temporary shell environment values.

The isolated Compose project remains running so the feature can be inspected
before merge. Its uniquely named smoke rows and S3 objects are confined to the
test database and bucket; no shared or production service was modified.

## Scope review

The branch diff was reviewed against the approved design. It contains no Java,
Maven, Spring Boot, source-repository fetcher, auto-publish path, ordinary-token
default-scope expansion, skill-owner transfer on later runs, removed-skill
deletion, or production MinIO/K8s workload. Scanner and namespace-owner review
remain mandatory.

## 2026-08-19 version submitter attribution follow-up

Branch `codex/oss-version-submitter-design` was rebuilt and verified against
the same complete Compose topology. The runtime images used were:

- backend: `sha256:28a8c155039615cace92b8e24c02421b0928b8b342f82073210b8b5a839fbba7`;
- web: `sha256:92e8007b50a3012931450b8fa9c6e23ee61f7c02f5b4dba57f24be86888488bf`;
- scanner: `sha256:a5010489ccf34e82cc98c9aef35ee42f65ff8384c25dc9b46becc505ca7d7363`.

Automated results:

- backend with `SKILLHUB_TEST_DATABASE_URL` pointing to PostgreSQL on port
  `55432`: `1422 passed, 10 skipped, 1 warning`;
- frontend: typecheck and lint passed, `217` Vitest files and `876` tests
  passed, and the production Vite build passed;
- targeted Ruff, Python compile, K8s render, release Compose render, test
  overlay render, and `git diff --check` passed.

After force-recreating backend, scanner, root web, and `/skillhub` web from
those images, all seven services were healthy. The migration command returned
`skillhub_flyway_v43_baseline`; direct backend, root proxy, and `/skillhub`
proxy health requests returned HTTP 200.

The importer smoke completed with:

```text
OSS source import smoke passed: run=4169b4b5eb02 initial=cc1611bf136a410abd6e5e4b28869d94de00ebba changed=d791565f57739e72edb8c759b743c8991f01d9e0
```

Runtime API assertions proved that the initial published version identifies
`OSS Smoke Trigger`, the later pending version identifies `OSS Smoke Trigger
Two`, both use `OSS_IMPORT`, and the skill owner remains the original
`oss-smoke-4169b4b5eb02-trigger`. A separate native published version returned
`NATIVE_SUBMISSION` with `Native Smoke Submitter` while retaining its distinct
`Native Smoke Owner`. Root and `/skillhub` returned identical attribution for
the published OSS version.

The final ten-minute log scan across PostgreSQL, Redis, MinIO, backend,
scanner, root web, and subpath web found no traceback, SQL syntax or database
operational error, unhandled exception, fatal, panic, or scanner task failure.

## 2026-08-24 superseded internal GitLab self-clone evidence

This section records the earlier same-day verification only. It is superseded
by the central `pull_pipeline` result below and is not current deployment
guidance.

The runner-side path was corrected to match the actual deployment model. The
GitHub repository is already migrated into the internal GitLab project before
this stage. The project contains the shell and Python importer and clones itself
through `CI_REPOSITORY_URL` at the exact `CI_COMMIT_SHA`. The user-supplied
GitHub URL is only upstream identity/provenance and namespace input; Runner does
not connect to GitHub. The job requires neither a dedicated importer image nor
an installed `skillhub-oss-import` command.

Focused automated results:

- importer configuration, clone, discovery, package, orchestration, client,
  GitLab template, and CLI tests: `23 passed`;
- source-import backend/API/docs regressions: `73 passed, 1 warning`;
- Ruff across importer source/tests and the operator-doc test: passed;
- GitLab wrapper/template plus Chinese SOP contract tests: `7 passed`;
- PowerShell smoke-script parse and `git diff --check`: passed.

The full-stack smoke used the generic `python:3.12-bookworm` image pulled as
digest `sha256:80f5d259a5969c86f6c92145d572de4a68c68e0edd28d4367dec0fb411b42af3`.
The image supplied Python, Git, CA certificates, and shell only. The temporary
internal GitLab-shaped source project contained the fixture skills plus the exact
checked-in
`deploy/gitlab/oss-source-import.sh` called the exact checked-in
`tools/oss-source-importer/run_import.py`. Runtime dependencies were installed
from `requirements-runtime.txt` into a separate writable directory.

Python cloned a unique credentialed internal GitLab-shaped
`CI_REPOSITORY_URL` into an isolated temporary checkout and shallow-fetched the
exact `CI_COMMIT_SHA`. For the smoke only, Git rewrote that internal URL to the
read-only mounted source project, making self-clone deterministic without any
GitHub access. The backend received only the canonical `https://github.com/...`
upstream identity plus verified internal GitLab source SHA/ref. The report was
also checked to prove the simulated GitLab job token was not present.

All seven required services were healthy during the run: PostgreSQL, Redis,
MinIO, scanner, Python backend, root proxy, and `/skillhub` proxy. The smoke
completed with:

```text
OSS source import smoke passed: run=1427888a4efb initial=7c82168239866350f804238f243e2bef4231e96d changed=d2f8176ea4239e4518001c8d5a259a0c7adeb791
```

It verified internal self-clone, exact CI commit/ref provenance, three skill
packages, PostgreSQL identity/audit/review/source rows, Redis-backed scanner
processing, MinIO bundle objects, root review/publish, idempotent retry,
changed-source import through `/skillhub`, and a second human importer without
skill-owner transfer. A final ten-minute scan of backend, scanner, root proxy,
and subpath proxy logs returned zero `ERROR`, traceback, SQLSTATE, or HTTP 5xx
matches.

## 2026-08-24 central pull_pipeline runner verification

The approved runtime is now:

```text
pull-pipeline-for-user
  -> central pull_pipeline
  -> pull_code (scan-passed Dev GitLab landing + pull-code.env)
  -> publish_skillhub
  -> SkillHub scanner and namespace-owner review
```

The publish job executes repository-owned Python from the central checkout,
reads `pull-code.env` as the authoritative handoff, clones the exact Dev GitLab
SHA, and keeps the original GitHub SHA separate for SkillHub provenance. It does
not use the central repository's own revision as source data.

Runtime package installation was removed. `run_import.py --help` passed under
`python -S`, the project has no production Python dependencies, and the shell
wrapper performs only Python/Git preflight before executing the checked-in
Python file. The obsolete importer Dockerfile and runtime requirements export
were removed.

Final automated results:

- importer tests: `41 passed`;
- importer Ruff: passed;
- Chinese operator SOP tests: `4 passed`;
- `uv lock --check`: resolved the expected 8 development packages;
- PowerShell smoke parser and Git Bash shell syntax: passed;
- shell byte check: zero CRLF and `.gitattributes` enforces `eol=lf`;
- `git diff --check`: passed.

Review-driven security coverage proves:

- missing, out-of-tree, oversized, invalid, conflicting, or control-character
  handoff data fails closed;
- a non-`PASSED` scan or scan/Dev SHA mismatch cannot submit;
- Dev GitLab clone URLs are credential-free HTTPS;
- `CI_JOB_TOKEN` is absent from Git command arguments, reports, and errors;
- Git and SkillHub HTTP redirects are disabled;
- SkillHub authorization, multipart, request ID, non-JSON, root path, and
  `/skillhub` behavior work through the standard-library HTTP adapter.

Docker daemon 29.5.2 was available. The final smoke mounted a temporary central
pipeline checkout and a separate Dev source checkout read-only into the stock
`python:3.12-bookworm` job container. No package install ran. PostgreSQL, Redis,
MinIO, scanner, Python backend, root proxy, and `/skillhub` proxy were healthy,
and the final run completed with:

```text
OSS source import smoke passed: run=54ed17c4bd22 initial=0c2cf683e796e276dd1244e00d0cf38bd2320637 changed=88778fed6dac8b8e7cdcebf0801707f34c812d16
```

The smoke verified authoritative artifact loading, exact Dev checkout, scan
evidence, three package imports, PostgreSQL identity/audit/review/source rows,
Redis-backed scanner processing, MinIO objects, approval and publication,
idempotent retry, a changed source through `/skillhub`, and stable ownership
across different human importers.

One external gate remains: run the template in the organization's real central
GitLab project and confirm the target Dev project job-token allowlist permits an
actual HTTPS clone. Local verification used a GitLab-shaped HTTPS URL rewritten
to the separate read-only Dev fixture, so it did not exercise the organization's
GitLab TLS, Runner policy, or allowlist configuration.

## 2026-08-25 branch handoff and Python 3.8 verification

The central importer no longer accepts source, Dev GitLab, or scan commit SHA
handoff variables. `pull-code.env` supplies the protected Dev GitLab branch;
the importer shallow-fetches that branch, detached-checks out `FETCH_HEAD`, and
derives the checked-out revision locally. The landing flow must preserve the
upstream commit object because SkillHub combines that derived revision with the
original GitHub URL for its provenance browse link.

The importer sends no `versionOverride`. When `SKILL.md` has no explicit
version, the Python backend now uses the existing publish workflow's UTC
`YYYYMMDDHHMMSS` fallback. Explicit versions and immutable-version conflict
behavior are unchanged.

The production importer remains standard-library-only and declares Python 3.8
support. Compatibility changes removed Python 3.9+ and 3.10+ runtime APIs. A
stock `python:3.8-bookworm` container ran the checked-in entrypoint with
`python -S` and no package installation; `run_import.py --help` exited 0.

Final automated results:

- importer tests: `44 passed` after the branch-name boundary was tightened to
  reject leading `-`;
- importer Ruff: passed;
- source-import backend tests: `23 passed`;
- complete backend suite: `1616 passed, 45 skipped`;
- Chinese operator contract tests: `4 passed`;
- `uv lock --check --offline`: resolved 14 development packages;
- release Compose config and `git diff --check`: passed.

Docker 29.5.2 rebuilt and recreated the Python backend while PostgreSQL, Redis,
MinIO, scanner, root proxy, and `/skillhub` proxy remained healthy. The complete
smoke then ran the importer under Python 3.8 with no runtime install and finished:

```text
OSS source import smoke passed: run=2641d1fab016 initial=260d44a8357f3e29b67ff644d6961c00c111bb70 changed=e238434a39aa5f0dc2a01fa70f1ce1c1093ce4c2
```

The smoke verified branch checkout, locally derived provenance, three imports,
the timestamp version fallback, PostgreSQL provenance/audit/review data,
Redis-backed scanning, MinIO objects, approval and publication, idempotent
retry, changed-source import through `/skillhub`, and stable ownership. Its
temporary root was retained rather than recursively removed:
`C:\Users\USER\AppData\Local\Temp\skillhub-oss-import-2641d1fab016`.

The remaining organization-only gate is unchanged: the real GitLab runner must
verify its approved Python 3.8 image, enterprise CA/TLS path, cross-project job
token allowlist, protected branch policy, commit-preserving landing flow, and
serialization or immutable per-pipeline branches when imports can overlap.

## 2026-08-26 GitLab job log verification

The importer now emits UTC, single-line job events for validated configuration,
Git clone stages, discovery, packaging, namespace setup, every skill validation
and submission, idempotent skips, report persistence, final status, exit code,
and aggregate counts. Dynamic values are JSON-quoted and bounded. Tests prove
that control characters cannot inject another log line and that SkillHub and
GitLab tokens never appear in console output.

Known failures log their stable status, exception class, safe error, and exit
code. Unexpected failures expose only the exception class. If the JSON report
path is not writable, the console now records `event=report_write_failed` and
the CLI still returns exit `10` instead of writing a fallback artifact elsewhere
or escaping with an uncontrolled exit.

Final automated results:

- importer tests: `50 passed`;
- importer Ruff: passed;
- Chinese operator contract tests: `4 passed`;
- stock `python:3.8-bookworm` with `python -S`: entrypoint help passed with no
  runtime installation;
- PowerShell smoke contract: job events present and both credential values
  absent.

The first runtime attempt exposed that the long-running smoke backend used a
stale image without the already-pushed timestamp fallback. The backend image
was rebuilt from current `dev` and only the server container was recreated;
PostgreSQL, Redis, MinIO, scanner, root proxy, `/skillhub` proxy, and their data
were preserved. The final complete smoke passed:

```text
OSS source import smoke passed: run=7533d96ebbf0 initial=7cc2db2d2c7f4105480ec7180e461a81d6ad40b6 changed=7a2f655c31e6e3e30038f5fe40cbc7b136f442fa
```

Its visible job output proved three initial imports, three idempotent retry
skips, and a `/skillhub` changed run with one import and two skips. PostgreSQL,
Redis-backed scanning, MinIO objects, approval/publication, ownership, request
IDs, timestamp fallback, root path, and subpath behavior remained valid. The
final temporary root was retained:
`C:\Users\USER\AppData\Local\Temp\skillhub-oss-import-7533d96ebbf0`.

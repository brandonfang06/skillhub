# Publish Upload Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the Python package extraction and validation foundation needed before Python
takes ownership of publish/upload routes.

**Architecture:** Do not migrate any publish route in this milestone. Build Python-only helpers that
mirror Java's zip extraction, package path normalization, content-type detection, `SKILL.md`
metadata parsing, and package validation behavior. Java remains the live contract reference and all
publish POST routes stay Java-owned until a later route-ownership milestone.

**Tech Stack:** FastAPI Python backend, Python 3.12, `uv`, pytest, `zipfile`, `pathlib`, PyYAML
through existing dependencies if already present or `uv add pyyaml` if missing, Vite proxy tests
only for ownership non-regression, Windows live gate for Java route ownership and Python helper
contract checks.

---

## Why This Is The Next Phase

Group B storage/download read path is complete. Group D publish/upload is the next major capability,
but a full route migration is too large for one safe milestone because Java publish currently owns:

- multipart archive extraction;
- package safety checks;
- `SKILL.md` frontmatter parsing;
- namespace writability and membership checks;
- skill/version/file DB mutations;
- object storage writes;
- bundle zip creation;
- review task creation;
- scanner trigger;
- replacement cleanup and storage compensation.

This foundation milestone moves only deterministic package parsing/validation logic into Python.
It creates the local building blocks for later publish route ownership while keeping all Java POST
routes active.

## Routes In Scope

No route ownership changes in this milestone.

Routes that must remain Java-owned:

- `POST /api/v1/skills`
- `POST /api/v1/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/cli/v1/skills/{namespace}/publish/validate`
- `POST /api/cli/v1/skills/{namespace}/publish`

Python helper tests may call pure Python functions only. Do not expose a new public API unless a
later milestone explicitly plans an internal diagnostics route.

## Java Reference Findings

### Portal Publish

Java `SkillPublishController` owns:

- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`

Request fields:

- `file`: multipart zip package.
- `visibility`: required, parsed with `SkillVisibility.valueOf(visibility.toUpperCase())`.
- `confirmWarnings`: optional boolean, default `false`.

Response:

- SkillHub envelope.
- message code: `response.success.published`.
- data fields:
  - `skillId`
  - `namespace`
  - `slug`
  - `version`
  - `status`
  - `fileCount`
  - `totalSize`

### ClawHub Compatibility Publish

Java `ClawHubCompatController` owns:

- `POST /api/v1/skills`
- `POST /api/v1/publish`

These routes use ClawHub plain response shapes, not SkillHub envelope shapes. They must remain
Java-owned until the Python publish transaction and compatibility response mapping are both planned.

### CLI Publish

Java `CliSkillController` owns:

- `POST /api/cli/v1/skills/{namespace}/publish/validate`
- `POST /api/cli/v1/skills/{namespace}/publish`

These routes share archive extraction with web publish but use CLI response DTOs and dry-run
semantics. Keep them Java-owned until the Python package foundation and publish transaction are
stable.

### Archive Extraction Rules

Java `SkillPackageArchiveExtractor` behavior to mirror first:

- Reject total upload size over configured `maxPackageSize`.
- Ignore directories.
- Ignore OS metadata entries:
  - `__MACOSX/`
  - `.DS_Store`
  - AppleDouble files whose basename starts with `._`
- Reject more than configured `maxFileCount` files.
- Normalize paths through `SkillPackagePolicy.normalizeEntryPath(...)`.
- Reject single file size over configured `maxSingleFileSize`.
- Determine content type by extension.
- Strip a single common root directory when every file is under that root.
- `extractWithWarnings(...)` promotes a single nested directory containing `SKILL.md` and warns for
  ignored files outside that directory.
- If multiple nested directories each contain `SKILL.md`, reject as ambiguous.

Java `ZipPackageExtractor` has overlapping but not identical behavior. For this milestone, mirror
`SkillPackageArchiveExtractor` because portal publish and ClawHub compatibility publish use it.

### Package Policy Rules

Mirror `SkillPackagePolicy`:

- `MAX_FILE_COUNT = 500`
- `MAX_SINGLE_FILE_SIZE = 10MB`
- `MAX_TOTAL_PACKAGE_SIZE = 100MB`
- root `SKILL.md` path is required for validation.
- accepted extensions are the Java allowlist in `SkillPackagePolicy.ALLOWED_EXTENSIONS`.
- path normalization rejects:
  - missing/blank path;
  - absolute path;
  - drive or scheme prefix containing `:`;
  - `.` / `..` / `../...`;
  - non-normalized paths such as `a/../b.md`.
- content signature validation warns for mismatches:
  - `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.ico`, `.pdf`;
  - `.svg` must be UTF-8 and contain `<svg`;
  - text-like extensions must be UTF-8 and not contain NUL bytes.

## Allowed Files

Create:

- `server-python/app/publish/package.py`
- `server-python/app/publish/__init__.py`
- `server-python/tests/test_publish_package.py`
- `docs/backend-python-migration/results/2026-06-08-publish-upload-foundation.md`

Modify:

- `server-python/app/core/config.py` if package limits need settings.
- `server-python/pyproject.toml` and `server-python/uv.lock` only if PyYAML is not already
  available and must be added with `uv add pyyaml`.
- `web/vite.config.test.ts` only to assert publish POST routes remain Java-owned.
- `scripts/dev-hybrid.ps1` to add `verify-publish-foundation-smoke`.
- `server-python/tests/test_hybrid_makefile.py` to cover the new smoke action.
- `docs/backend-python-migration/migration-sequence-plan.md`.
- `docs/backend-python-migration/route-registry.md` only to clarify Java-owned publish boundaries.
- `docs/backend-python-migration/windows-live-verification.md`.

Forbidden:

- Do not modify any file under `server/`.
- Do not change Vite proxy ownership for publish POST routes.
- Do not create or update DB rows from Python in this milestone.
- Do not write object storage files from Python in this milestone.
- Do not trigger scanner from Python in this milestone.

## Data Access Strategy

No database access in this milestone.

This milestone is pure package parsing/validation plus ownership non-regression. DB writes begin in
a later publish transaction milestone after the package foundation has a passing test and live gate.

## Task 1. Python Package Model And Content Type Detection

**Files:**

- Create: `server-python/app/publish/package.py`
- Create: `server-python/app/publish/__init__.py`
- Test: `server-python/tests/test_publish_package.py`

- [ ] Write failing tests:
  - `PackageEntry(path="SKILL.md", content=b"# skill", content_type="text/markdown")` exposes
    `size == 7`.
  - `determine_content_type("src/main.py") == "text/x-python"`.
  - `determine_content_type("README.md") == "text/markdown"`.
  - `determine_content_type("assets/icon.png") == "image/png"`.
  - `determine_content_type("unknown.bin") == "application/octet-stream"`.

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_publish_package.py -q
```

Expected before implementation: import or function not found.

- [ ] Implement:
  - immutable `PackageEntry` dataclass with `path`, `content`, `content_type`, and computed
    `size`.
  - `determine_content_type(path: str) -> str` with Java-compatible extension mapping from
    `SkillPackageArchiveExtractor`.

- [ ] Re-run focused tests and expect pass.

## Task 2. Path Normalization And OS Metadata Filtering

**Files:**

- Modify: `server-python/app/publish/package.py`
- Test: `server-python/tests/test_publish_package.py`

- [ ] Add failing tests:
  - `normalize_entry_path("SKILL.md") == "SKILL.md"`.
  - `normalize_entry_path("dir/SKILL.md") == "dir/SKILL.md"`.
  - rejects `""`, `"/SKILL.md"`, `"../SKILL.md"`, `"dir/../SKILL.md"`,
    `"C:/temp/SKILL.md"`.
  - converts backslashes to forward slashes before validation, matching `SkillPackagePolicy`.
  - `is_os_metadata_entry("__MACOSX/._SKILL.md") is True`.
  - `is_os_metadata_entry(".DS_Store") is True`.
  - `is_os_metadata_entry("docs/._README.md") is True`.
  - `is_os_metadata_entry("docs/README.md") is False`.

Run focused test and expect failure.

- [ ] Implement:
  - `normalize_entry_path(raw_path: str) -> str`.
  - `is_os_metadata_entry(raw_path: str) -> bool`.

- [ ] Re-run focused tests and expect pass.

## Task 3. Zip Extraction And Root Promotion

**Files:**

- Modify: `server-python/app/publish/package.py`
- Test: `server-python/tests/test_publish_package.py`

- [ ] Add failing tests with in-memory zip bytes:
  - skips directories and OS metadata entries.
  - extracts `SKILL.md` and `src/main.py` with exact bytes and content types.
  - rejects more than `max_file_count`.
  - rejects a single file over `max_single_file_size`.
  - rejects total package over `max_total_package_size`.
  - strips a single common root directory: `demo/SKILL.md` becomes `SKILL.md`.
  - `extract_package_with_warnings(...)` promotes `demo/SKILL.md` when root `SKILL.md` is missing
    and returns warning `Ignored file outside skill directory: notes.txt`.
  - rejects ambiguous nested `SKILL.md` directories with message starting
    `Ambiguous package: SKILL.md found in multiple directories`.

Run focused test and expect failure.

- [ ] Implement:
  - `PackageLimits(max_total_package_size, max_single_file_size, max_file_count)`.
  - `extract_package(zip_bytes: bytes, limits: PackageLimits) -> list[PackageEntry]`.
  - `strip_single_root_directory(entries: list[PackageEntry]) -> list[PackageEntry]`.
  - `extract_package_with_warnings(zip_bytes: bytes, limits: PackageLimits)
    -> tuple[list[PackageEntry], list[str]]`.
  - `promote_single_skill_md_directory(entries: list[PackageEntry])
    -> tuple[list[PackageEntry], list[str]]`.

- [ ] Re-run focused tests and expect pass.

## Task 4. Package Validation And SKILL.md Metadata Parsing

**Files:**

- Modify: `server-python/app/publish/package.py`
- Test: `server-python/tests/test_publish_package.py`

- [ ] Add failing tests:
  - missing root `SKILL.md` returns error `Missing required file: SKILL.md at root`.
  - duplicate path returns error `Duplicate package entry path: SKILL.md`.
  - disallowed extension returns warning `Disallowed file extension: binary.exe`.
  - invalid UTF-8 text file returns warning `File content does not match extension: README.md`.
  - invalid PNG signature returns warning `File content does not match extension: icon.png`.
  - valid `SKILL.md` frontmatter with `name`, `description`, `version` parses resolved metadata.
  - missing required `name` or `description` returns Java-compatible invalid frontmatter wording.

Run focused test and expect failure.

- [ ] Implement:
  - `ValidationResult(valid: bool, errors: list[str], warnings: list[str])`.
  - `SkillMetadata(name: str, description: str, version: str | None, body: str,
    frontmatter: dict[str, object])`.
  - `parse_skill_metadata(content: bytes) -> SkillMetadata`.
  - `validate_package(entries: list[PackageEntry], limits: PackageLimits) -> ValidationResult`.
  - content signature helpers matching Java's warning behavior.

- [ ] Re-run focused tests and expect pass.

## Task 5. Publish Route Ownership Non-Regression

**Files:**

- Modify: `web/vite.config.test.ts`
- Test: `web/vite.config.test.ts`

- [ ] Add failing Vite config assertions:
  - `POST /api/v1/skills` resolves to Java.
  - `POST /api/v1/publish` resolves to Java.
  - `POST /api/v1/skills/global/publish` resolves to Java.
  - `POST /api/web/skills/global/publish` resolves to Java.
  - existing Python-owned GET routes remain Python-owned.

Run:

```powershell
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
```

Expected before update: missing assertions only; existing tests pass.

- [ ] Update assertions only. Do not change proxy targets unless a test reveals accidental publish
  ownership.

- [ ] Re-run Vite proxy test and expect pass.

## Task 6. Windows Live Gate For Foundation

**Files:**

- Modify: `scripts/dev-hybrid.ps1`
- Modify: `server-python/tests/test_hybrid_makefile.py`
- Modify: `docs/backend-python-migration/windows-live-verification.md`

- [ ] Add `verify-publish-foundation-smoke` action.

The gate must:

- start Java/Python/Vite hybrid stack;
- verify Java still owns publish POST paths through Vite by checking status parity for requests
  without auth/session:
  - `POST /api/v1/skills`
  - `POST /api/v1/publish`
  - `POST /api/v1/skills/global/publish`
  - `POST /api/web/skills/global/publish`
- run Python package foundation tests:
  - `uv run pytest tests/test_publish_package.py -q`;
- run Playwright smoke;
- write `.dev/publish-foundation-contract-result.json`.

- [ ] Update `test_hybrid_makefile.py` to assert:
  - `verify-publish-foundation-smoke` is in `ValidateSet`;
  - `Invoke-PublishFoundationContractComparison` exists;
  - `publish-foundation-contract-result.json` is written.

- [ ] Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_hybrid_makefile.py -q
```

Expected: pass.

## Task 7. Docs, Verification, Commit

**Files:**

- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Modify: `docs/backend-python-migration/route-registry.md` if route boundary notes changed.
- Create: `docs/backend-python-migration/results/2026-06-08-publish-upload-foundation.md`

- [ ] Update migration sequence:
  - mark this as the first Group D foundation milestone;
  - keep all publish POST routes Java-owned;
  - state that no DB writes or storage writes are performed by Python yet.

- [ ] Write result doc with:
  - routes changed: none;
  - owner before/after: publish POST remains Java;
  - files changed;
  - tests run;
  - risks;
  - follow-up milestone.

- [ ] Run full verification:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

```powershell
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
.\node_modules\.bin\tsc.CMD --noEmit
```

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-foundation-smoke
```

```powershell
git diff --check
git diff --name-only -- server
```

Expected:

- all tests pass;
- live gate passes;
- `git diff --name-only -- server` prints nothing.

- [ ] Commit:

```powershell
git add server-python/app/publish server-python/tests/test_publish_package.py `
  server-python/tests/test_hybrid_makefile.py web/vite.config.test.ts `
  scripts/dev-hybrid.ps1 docs/backend-python-migration
git commit -m "feat(publish): add package validation foundation"
git push origin dev
```

## Acceptance Criteria

- Python has package extraction and validation helpers matching Java's deterministic package rules.
- No publish POST route ownership changes.
- Vite tests prove publish POST routes still fall through to Java.
- Windows live gate proves Vite publish POST status behavior still matches direct Java.
- Python package foundation tests pass.
- Full Python pytest, Vite proxy tests, TypeScript typecheck, and Playwright smoke pass.
- `server/` remains untouched.

## Follow-Up Milestones

After this foundation passes, split Group D into these implementation milestones:

1. Publish transaction dry-run model:
   - namespace lookup;
   - membership/platform role checks;
   - slug/version conflict checks;
   - no DB writes.
2. Local storage write transaction:
   - create skill/version/file rows;
   - write `skills/{skillId}/{versionId}/{path}`;
   - build and write `packages/{skillId}/{versionId}/bundle.zip`;
   - no scanner trigger yet.
3. Portal publish route ownership:
   - `POST /api/v1/skills/{namespace}/publish`;
   - `POST /api/web/skills/{namespace}/publish`;
   - live Java/Python/Vite comparison with deterministic zip fixture.
4. ClawHub/CLI publish compatibility:
   - `POST /api/v1/skills`;
   - `POST /api/v1/publish`;
   - CLI validate/publish routes only after response contracts are explicitly mapped.
5. Scanner/review integration:
   - review task creation;
   - scanner trigger;
   - scan result handling;
   - event/audit behavior.

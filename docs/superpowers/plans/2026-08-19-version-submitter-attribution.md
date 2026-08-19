# Version Submitter Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the human submitter for every selected Skill Detail version while preserving stable skill ownership and keeping the OSS service principal as an audit-only actor.

**Architecture:** Extend the existing Skill Version Detail read model without a schema change. The backend query resolves OSS attribution from `local_oss_skill_version_source.imported_by`, native attribution from the latest applicable `review_task.submitted_by`, and `skill_version.created_by` as a compatibility fallback; the frontend renders the common attribution next to native version metadata or inside the OSS Source Provenance card.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy text queries, PostgreSQL 16, React 19, TypeScript, i18next, Tailwind CSS, Vitest, pytest, Docker Compose.

---

## File Map

- Modify `server-python/app/skills/read_repository.py`: select deterministic version attribution and the current display name in the existing version-detail query.
- Modify `server-python/app/skills/read_responses.py`: map nullable row fields into the common `versionAttribution` response.
- Modify `server-python/tests/test_skill_version_detail_repository.py`: unit-contract coverage for OSS, native, and unresolved attribution.
- Modify `server-python/tests/test_skill_version_detail.py`: query-shape and route-envelope regression coverage.
- Create `server-python/tests/test_skill_version_attribution_postgres.py`: real PostgreSQL proof of owner stability and per-version attribution.
- Modify `web/src/api/types.ts`: add the compatibility-route `VersionAttribution` type.
- Create `web/src/features/skill/version-attribution.tsx`: reusable native submission card and attribution details.
- Create `web/src/features/skill/version-attribution.test.tsx`: native/OSS/empty/name-fallback/long-name behavior.
- Modify `web/src/features/skill/source-provenance.tsx`: render OSS importer attribution in the provenance card.
- Modify `web/src/features/skill/source-provenance.test.tsx`: prove importer name and timestamp display.
- Modify `web/src/pages/skill-detail.tsx`: pass the selected version's attribution and show native attribution.
- Modify `web/src/pages/skill-detail.test.tsx`: prove selected/latest attribution is wired to the page.
- Modify `web/src/i18n/locales/en.json`, `zh.json`, and `zh-TW.json`: add all attribution copy in three locales.
- Modify `docs/backend-python-maintenance/oss-source-import-verification.md`: record the visible imported-by acceptance check.

### Task 1: Backend Response Contract

**Files:**
- Modify: `server-python/tests/test_skill_version_detail_repository.py`
- Modify: `server-python/app/skills/read_responses.py`

- [ ] **Step 1: Write failing response-mapping tests**

Add an OSS row with these fields and assert the exact response:

```python
row.update(
    {
        "version_attribution_type": "OSS_IMPORT",
        "version_submitted_by": "trigger-user",
        "version_submitted_by_name": "hcfange",
        "version_submitted_at": datetime(2026, 8, 19, 8, 0, tzinfo=UTC),
    }
)
assert build_version_detail_response(row)["versionAttribution"] == {
    "type": "OSS_IMPORT",
    "submittedBy": "trigger-user",
    "submittedByName": "hcfange",
    "submittedAt": "2026-08-19T08:00:00Z",
}
```

Add separate tests for `NATIVE_SUBMISSION`, a null display name, and a row whose `version_submitted_by` is null. The null row must return `versionAttribution: None`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd server-python
uv run pytest tests/test_skill_version_detail_repository.py -q
```

Expected: failures because `versionAttribution` is absent.

- [ ] **Step 3: Implement the minimal mapper**

In `read_responses.py`, add:

```python
def build_version_attribution_response(row: dict[str, Any]) -> dict[str, object] | None:
    submitted_by = row.get("version_submitted_by")
    submitted_at = row.get("version_submitted_at")
    attribution_type = row.get("version_attribution_type")
    if submitted_by is None or submitted_at is None or attribution_type not in {
        "NATIVE_SUBMISSION",
        "OSS_IMPORT",
    }:
        return None
    return {
        "type": str(attribution_type),
        "submittedBy": str(submitted_by),
        "submittedByName": (
            str(row["version_submitted_by_name"])
            if row.get("version_submitted_by_name") is not None
            else None
        ),
        "submittedAt": to_java_instant(submitted_at),
    }
```

Add `"versionAttribution": build_version_attribution_response(row)` to `build_version_detail_response` and export the helper.

- [ ] **Step 4: Run tests and verify GREEN**

Run the same pytest command. Expected: all tests pass.

- [ ] **Step 5: Commit the response contract**

```powershell
git add server-python/app/skills/read_responses.py server-python/tests/test_skill_version_detail_repository.py
git commit -m "feat(skill): expose version submitter attribution"
```

### Task 2: Deterministic Version-Detail Query

**Files:**
- Modify: `server-python/tests/test_skill_version_detail.py`
- Modify: `server-python/app/skills/read_repository.py`

- [ ] **Step 1: Write failing query-shape tests**

Extend the fake connection assertion to require the version-detail SQL to contain:

```python
assert "LEFT JOIN LATERAL" in sql
assert "FROM review_task" in sql
assert "version_source.imported_by" in sql
assert "version_submitted_by" in sql
```

Return attribution aliases from the fake row and assert that the owner-preview response includes `versionAttribution` without changing `sourceProvenance`.

- [ ] **Step 2: Run the focused test and verify RED**

```powershell
cd server-python
uv run pytest tests/test_skill_version_detail.py::test_read_skill_version_detail_allows_owner_preview_without_latest_pointer -q
```

Expected: failure because the query has no review or imported-by attribution fields.

- [ ] **Step 3: Implement the SQL read model**

Extend the existing `SELECT` with:

```sql
CASE
    WHEN version_source.id IS NOT NULL THEN 'OSS_IMPORT'
    ELSE 'NATIVE_SUBMISSION'
END AS version_attribution_type,
COALESCE(version_source.imported_by, version_review.submitted_by, sv.created_by)
    AS version_submitted_by,
submitter.display_name AS version_submitted_by_name,
COALESCE(version_source.imported_at, version_review.submitted_at, sv.created_at)
    AS version_submitted_at
```

Add a lateral review join that deterministically selects the latest task for the version:

```sql
LEFT JOIN LATERAL (
    SELECT rt.submitted_by, rt.submitted_at
    FROM review_task rt
    WHERE rt.skill_version_id = sv.id
    ORDER BY rt.submitted_at DESC, rt.id DESC
    LIMIT 1
) version_review ON TRUE
LEFT JOIN user_account submitter
  ON submitter.id = COALESCE(
      version_source.imported_by,
      version_review.submitted_by,
      sv.created_by
  )
```

Keep SQL in `read_repository.py`; do not move it into the route.

- [ ] **Step 4: Run focused backend tests**

```powershell
cd server-python
uv run pytest tests/test_skill_version_detail.py tests/test_skill_version_detail_repository.py -q
uv run ruff check app/skills/read_repository.py app/skills/read_responses.py tests/test_skill_version_detail.py tests/test_skill_version_detail_repository.py
```

Expected: all pass with no lint findings.

- [ ] **Step 5: Commit the query**

```powershell
git add server-python/app/skills/read_repository.py server-python/tests/test_skill_version_detail.py
git commit -m "feat(skill): resolve version submitters"
```

### Task 3: PostgreSQL Attribution Proof

**Files:**
- Create: `server-python/tests/test_skill_version_attribution_postgres.py`

- [ ] **Step 1: Write a real PostgreSQL integration test**

Use the existing PostgreSQL test URL helper and migration fixture pattern. Insert:

- one ACTIVE namespace and namespace OWNER;
- an original skill owner `alice`;
- two `skill_version` rows owned by the same skill;
- a native review task submitted by `bob`;
- an OSS source version imported by `hcfange` and acted on by a service principal.

Call `read_skill_version_detail` for both versions and assert:

```python
assert native["versionAttribution"]["submittedBy"] == bob_id
assert native["versionAttribution"]["type"] == "NATIVE_SUBMISSION"
assert imported["versionAttribution"]["submittedBy"] == hcfange_id
assert imported["versionAttribution"]["type"] == "OSS_IMPORT"
assert imported["sourceProvenance"]["repositoryRevisionSha"] == commit_sha
```

Read `skill.owner_id` afterward and assert it is still `alice`.

- [ ] **Step 2: Run the PostgreSQL proof**

```powershell
cd server-python
$env:SKILLHUB_TEST_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub_smoke_db@127.0.0.1:55432/skillhub'
uv run pytest tests/test_skill_version_attribution_postgres.py -q
```

Expected: pass against PostgreSQL. This supplements the RED/GREEN response and
query tests from Tasks 1 and 2; it does not introduce a new production behavior.

- [ ] **Step 3: Complete fixtures or query corrections only as required**

Do not add a schema column. If attribution is not deterministic from the current tables, stop execution and revise the design before adding a migration.

- [ ] **Step 4: Run the integration test and verify GREEN**

Run the same command. Expected: pass against PostgreSQL.

- [ ] **Step 5: Commit PostgreSQL coverage**

```powershell
git add server-python/tests/test_skill_version_attribution_postgres.py
git commit -m "test(skill): verify version attribution in postgres"
```

### Task 4: Frontend Type And Attribution Components

**Files:**
- Modify: `web/src/api/types.ts`
- Create: `web/src/features/skill/version-attribution.tsx`
- Create: `web/src/features/skill/version-attribution.test.tsx`
- Modify: `web/src/features/skill/source-provenance.tsx`
- Modify: `web/src/features/skill/source-provenance.test.tsx`

- [ ] **Step 1: Write failing component tests**

Define the desired API in tests:

```tsx
const attribution = {
  type: 'OSS_IMPORT' as const,
  submittedBy: 'trigger-user',
  submittedByName: 'hcfange',
  submittedAt: '2026-08-19T08:00:00Z',
}

const html = renderToStaticMarkup(
  <SourceProvenanceCard provenance={provenance} attribution={attribution} />,
)
expect(html).toContain('Imported by')
expect(html).toContain('hcfange')
```

Add native tests for `VersionAttributionCard`, a missing attribution returning no markup, display-name fallback to user ID, and a long display name remaining present without truncation.

- [ ] **Step 2: Run tests and verify RED**

```powershell
cd web
corepack pnpm exec vitest run src/features/skill/version-attribution.test.tsx src/features/skill/source-provenance.test.tsx
```

Expected: missing module/prop/type failures.

- [ ] **Step 3: Add the compatibility type**

In `web/src/api/types.ts`:

```typescript
export interface VersionAttribution {
  type: 'NATIVE_SUBMISSION' | 'OSS_IMPORT'
  submittedBy: string
  submittedByName?: string | null
  submittedAt: string
}
```

Add `versionAttribution?: VersionAttribution | null` to `SkillVersionDetail`.

- [ ] **Step 4: Implement focused components**

`VersionAttributionCard` renders only native attribution and uses
`submittedByName || submittedBy`. `SourceProvenanceCard` accepts an optional
attribution prop and renders imported-by details only when its type is
`OSS_IMPORT`. Use `break-words`/`min-w-0`; do not truncate names.

- [ ] **Step 5: Run focused tests, typecheck, and lint**

```powershell
cd web
corepack pnpm exec vitest run src/features/skill/version-attribution.test.tsx src/features/skill/source-provenance.test.tsx
corepack pnpm run typecheck
corepack pnpm exec eslint src/api/types.ts src/features/skill/version-attribution.tsx src/features/skill/version-attribution.test.tsx src/features/skill/source-provenance.tsx src/features/skill/source-provenance.test.tsx --max-warnings 0
```

Expected: all commands pass.

- [ ] **Step 6: Commit frontend components**

```powershell
git add web/src/api/types.ts web/src/features/skill/version-attribution.tsx web/src/features/skill/version-attribution.test.tsx web/src/features/skill/source-provenance.tsx web/src/features/skill/source-provenance.test.tsx
git commit -m "feat(skill): display version submitters"
```

### Task 5: Skill Detail Wiring And Three Locales

**Files:**
- Modify: `web/src/pages/skill-detail.test.tsx`
- Modify: `web/src/pages/skill-detail.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`

- [ ] **Step 1: Make the version-detail hook controllable in the page test**

Add `useSkillVersionDetailMock` beside the existing query mocks and return it
from the mocked hook. Reset it in `beforeEach` with `{ data: undefined }`.

- [ ] **Step 2: Write failing page tests**

Return native attribution and assert `Submitted by` plus the name is rendered.
Return OSS attribution plus provenance and assert `Imported by` is rendered and
the native card is absent. Assert the visible skill owner remains `Owner One`.

- [ ] **Step 3: Run the page test and verify RED**

```powershell
cd web
corepack pnpm exec vitest run src/pages/skill-detail.test.tsx
```

Expected: attribution labels are absent.

- [ ] **Step 4: Wire selected-version attribution**

Render:

```tsx
<VersionAttributionCard attribution={selectedVersionDetail?.versionAttribution} />
<SourceProvenanceCard
  provenance={selectedVersionDetail?.sourceProvenance}
  attribution={selectedVersionDetail?.versionAttribution}
/>
```

`VersionAttributionCard` must return null for OSS attribution so the person is
shown once, inside Source Provenance.

- [ ] **Step 5: Add exact translation keys in all three locales**

Add `skillDetail.versionAttributionTitle`, `skillDetail.submittedBy`,
`skillDetail.importedBy`, and `skillDetail.submittedAt` with natural English,
Simplified Chinese, and Traditional Chinese copy.

- [ ] **Step 6: Run focused and frontend gates**

```powershell
cd web
corepack pnpm exec vitest run src/pages/skill-detail.test.tsx src/features/skill/version-attribution.test.tsx src/features/skill/source-provenance.test.tsx
corepack pnpm run typecheck
corepack pnpm run lint
```

Expected: all pass.

- [ ] **Step 7: Commit page wiring and locales**

```powershell
git add web/src/pages/skill-detail.tsx web/src/pages/skill-detail.test.tsx web/src/i18n/locales/en.json web/src/i18n/locales/zh.json web/src/i18n/locales/zh-TW.json
git commit -m "feat(skill): show selected version attribution"
```

### Task 6: Documentation And Full Verification

**Files:**
- Modify: `docs/backend-python-maintenance/oss-source-import-verification.md`

- [ ] **Step 1: Update verification documentation**

Document that the selected version shows its human importer, the service
principal remains audit-only, and a later import by another user does not
change `skill.owner_id`.

- [ ] **Step 2: Run complete automated gates**

```powershell
cd server-python
$env:SKILLHUB_TEST_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub_smoke_db@127.0.0.1:55432/skillhub'
uv run pytest tests -q
uv run ruff check app tests

cd ../web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test

cd ..
kubectl kustomize deploy/k8s/base | Out-Null
docker compose --env-file .env.release.example -f compose.release.yml config | Out-Null
git diff --check dev...HEAD
```

Expected: all suites and render checks pass.

- [ ] **Step 3: Build and start the complete runtime**

Use the existing non-destructive smoke override and project name:

```powershell
docker compose -p skillhub-oss-import-smoke --env-file .env.release.example -f compose.release.yml -f docker-compose.oss-source-import-test.yml build server web web-subpath skill-scanner
docker compose -p skillhub-oss-import-smoke --env-file .env.release.example -f compose.release.yml -f docker-compose.oss-source-import-test.yml up -d
docker compose -p skillhub-oss-import-smoke --env-file .env.release.example -f compose.release.yml -f docker-compose.oss-source-import-test.yml ps
```

Require PostgreSQL, Redis, MinIO, scanner, backend, root web, and subpath web to
report healthy.

- [ ] **Step 4: Run real API/PostgreSQL acceptance**

Run `scripts/oss-source-import-smoke-test.ps1`, then query the selected imported
version detail over HTTP. Verify:

- `versionAttribution.type == OSS_IMPORT`;
- `versionAttribution.submittedBy` is the trigger user;
- the source commit/path remains correct;
- the database `skill.owner_id` is unchanged;
- root `/` and `/skillhub/` return HTTP 200;
- backend/scanner logs contain no traceback, SQL, or runtime errors.

- [ ] **Step 5: Commit documentation**

```powershell
git add docs/backend-python-maintenance/oss-source-import-verification.md
git commit -m "docs(skill): verify version submitter attribution"
```

- [ ] **Step 6: Final branch audit**

```powershell
git status --short
git diff --check dev...HEAD
git log --oneline dev..HEAD
git diff --stat dev...HEAD
```

Expected: clean worktree, only intended files, and no whitespace errors.

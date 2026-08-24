# Namespace security analytics verification

Date: 2026-08-24

Branch: `codex/namespace-security-analytics`

Baseline: `decb1b5c`

Design: `docs/backend-python-maintenance/plans/2026-08-24-namespace-security-analytics-design.md`

## Delivered behavior

- `/admin/namespace-analytics` now has URL-backed Catalog and Security views.
- The Security view is restricted to authenticated `SUPER_ADMIN` sessions and
  rejects bearer API tokens at the same boundary as the existing analytics
  page.
- The default inventory includes retained ACTIVE, FROZEN, and ARCHIVED
  namespaces; ACTIVE and ARCHIVED skills; public, namespace-only, and private
  visibility; visible and platform-hidden skills; and every retained version
  lifecycle state.
- Namespace totals count affected namespaces, skills, versions, and finding
  instances. Severity totals include CRITICAL, HIGH, MEDIUM, LOW, INFO, and
  UNCLASSIFIED findings.
- Only the latest active audit for each retained version and scanner is counted.
  Deleted versions, superseded scans, and soft-deleted audits are excluded.
- Namespace rows lazily load paginated affected-skill and version metadata.
  Finding descriptions, file locations, snippets, and remediation stay out of
  aggregate payloads and load only through the existing authorized per-version
  audit endpoint.
- All filters and paging are URL-backed, and both root-path and `/skillhub`
  deployments preserve their base path.
- English, Simplified Chinese, and Traditional Chinese copy is included.
- No schema migration, environment variable, Java runtime, or deployment
  contract change was introduced.

## Automated verification

### Python backend

Focused Namespace Analytics and security-audit regression:

```powershell
uv run --no-cache pytest tests/test_namespace_security_analytics.py tests/test_namespace_analytics.py tests/test_security_audit.py -q
```

Result: `71 passed, 1 existing Starlette/httpx deprecation warning`.

Complete backend regression:

```powershell
uv run --no-cache pytest tests -q
```

Result: `1616 passed, 45 skipped, 1 existing warning`.

Ruff passed after import ordering was corrected:

```powershell
uv run --no-cache ruff check app tests
```

### Real PostgreSQL invariant

```powershell
uv run --no-cache pytest tests/test_namespace_security_analytics_postgres.py -q
```

Result: `1 passed` against PostgreSQL. The transaction seeded and proved:

- ACTIVE and ARCHIVED namespaces and skills;
- private, hidden, and public inventory;
- all eight retained version states;
- multiple scanners and superseded scan rounds;
- soft-deleted audit exclusion;
- exact severity and unclassified counts.

The final aggregate was exactly 2 affected namespaces, 2 affected skills, 9
affected versions, and 10 finding instances. The severity split was CRITICAL 2,
HIGH 3, MEDIUM 2, LOW 1, INFO 1, and UNCLASSIFIED 1.

### React frontend

```powershell
corepack pnpm run test
corepack pnpm run typecheck
corepack pnpm run lint
```

Results:

- Vitest: `228` files and `929` tests passed.
- Typecheck passed.
- ESLint passed.
- The production Vite build passed with only the existing runtime-config,
  Browserslist-age, and chunk-size warnings.
- Focused tests cover URL defaults, filters, lazy namespace expansion, child
  pagination, disclosure boundaries, version-detail loading, and all three
  locales.

The focused Namespace Analytics OpenAPI JSON and generated TypeScript schema
were regenerated twice. Their hashes remained identical, proving generation is
current and idempotent.

## Query-plan verification

The production aggregate query was explained against both isolated PostgreSQL
fixtures. It used `idx_security_audit_version_type_latest` together with primary
key indexes.

| Runtime | Planning | Execution |
| --- | ---: | ---: |
| Root path | 4.413 ms | 0.636 ms |
| `/skillhub` | 4.541 ms | 0.631 ms |

No additional database index or migration was required.

## Integrated runtime acceptance

Two isolated production-image environments remain running for manual
acceptance. Each contains PostgreSQL, Redis, the Python scanner, the Python
backend with the scan consumer enabled, and the Nginx web image. The existing
local MinIO service was also healthy; this read-only analytics path does not
perform object-storage reads.

| Route model | Web URL | API | PostgreSQL | Redis |
| --- | --- | --- | --- | --- |
| Root | `http://127.0.0.1:61101/admin/namespace-analytics?view=security` | `61100` | `57532` | `57479` |
| Sub-path | `http://127.0.0.1:61103/skillhub/admin/namespace-analytics?view=security` | `61102` | `57533` | `57480` |

Authenticated browser acceptance proved:

- unauthenticated users return to the exact Security URL after login;
- both environments render the exact 2 / 2 / 9 / 10 fixture totals;
- archived, private, and hidden skills remain visible to the platform admin;
- all eight version states and multiple scanners appear in the drill-down;
- the CRITICAL filter changes both URL state and totals correctly;
- finding snippets appear only after opening an individual version detail;
- Catalog/Security switching remains inside `/skillhub` without a doubled
  prefix or root-path escape;
- both browser consoles had zero application warnings or errors.

After the final production web rebuild, all ten isolated containers were
healthy. A log scan across both web, backend, and scanner sets found no HTTP
5xx, SQL syntax error, SQLSTATE, traceback, or exception. The expected
unauthenticated `/auth/me` 401 responses occurred only before login.

## Deployment checks

The following production images built successfully:

- `skillhub-server-python:namespace-security-verify`
- `skillhub-web:namespace-security-verify`
- `skillhub-scanner:namespace-security-verify`

These checks also passed:

```powershell
docker compose --env-file .env.release.example -f compose.release.yml config
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/overlays/external
git diff --check
```

## Handoff status

Implementation and verification are complete in the isolated worktree. The
runtime environments are intentionally still running for user acceptance. No
commit, push, merge, deployment, or pull request was performed.

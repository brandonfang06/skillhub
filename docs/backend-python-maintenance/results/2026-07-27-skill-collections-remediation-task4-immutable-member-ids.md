# Skill Collections Remediation Task 4 Result

Date: 2026-07-27

Task: Use immutable Skill and Skill-version IDs for collection membership.

## Scope and boundary

This task changes the collection draft member contract, exact member
resolution, GitLab import draft seeding, collection maintenance UI identity,
and a new read-only Web endpoint used to discover versions by immutable Skill
ID.

The existing namespace/slug Skill detail, version, compare, file, download,
publish, lifecycle, scanner, CLI, and collection resolve routes remain
unchanged. No schema migration, deployment setting, feature flag, or existing
Skill coordinate was changed.

Task 5 repository-ingest claims were not started.

## Result

- `CollectionMemberInput` accepts only `skillId`, `skillVersionId`,
  `position`, and optional `note`.
- Draft validation rejects non-positive IDs, duplicate Skill IDs, and duplicate
  positions before opening a transaction.
- Member resolution requires the exact Skill/version pair:

  ```sql
  WHERE s.id = :skill_id
    AND sv.id = :skill_version_id
    AND sv.skill_id = s.id
    AND s.namespace_id = :namespace_id
  ```

- The referenced Skill must be active and visible; the version must be
  published, download-ready, and not yanked.
- Slug, version, owner, and visibility snapshots come only from the resolved
  database row.
- Mismatched Skill/version IDs and Skills outside the collection namespace
  both return `400 error.collection.member.notFound`.
- GitLab repository ingest passes the publisher's exact `skill_id` and
  `skill_version_id` into draft seeding without a slug/version round trip.
- The maintenance UI uses Skill and version IDs for selection values, query
  identity, duplicate detection, update suggestions, request payloads, and
  React keys. Coordinates remain display labels only.
- Version discovery uses the additive read-only endpoint
  `GET /api/web/skill-versions/by-skill-id/{skill_id}`. This separate path
  family cannot shadow a valid namespace/slug coordinate. The existing
  namespace/slug endpoint remains unchanged for core Skill pages.
- The editor and update suggestion show only versions that are both
  `PUBLISHED` and download-ready.
- A draft containing a deleted/degraded reference retains its snapshot and
  exposes an explicit remove action while leaving the editor available for a
  replacement. Save remains blocked until every locally retained member has
  exact IDs. Publish remains blocked until the repaired draft is persisted and
  the server detail confirms no degraded member remains.
- Coordinate and by-ID version resolution share one access, lifecycle,
  ordering, pagination, and response helper so their behavior cannot drift.
- Generated OpenAPI includes the ID-only member input and the by-ID version
  endpoint.

## TDD evidence

The initial backend RED run demonstrated the old coordinate contract and
coordinate lookup:

```text
6 failed, 27 passed, 1 warning
```

The initial frontend RED run demonstrated slug-based duplicate detection and
payload identity:

```text
2 files failed; 3 failed, 3 passed
```

An independent specification review then found that version discovery still
used namespace/slug after the request payload had moved to IDs. The valid RED
cases reproduced both parts of that gap:

```text
Backend: 2 failed, 8 passed
Frontend: 2 failed, 2 passed
```

The frontend RED included two different Skill IDs sharing the same displayed
slug. Neither caused a by-ID version query before the fix.

A separate installability RED case proved that a published but not
download-ready version was incorrectly suggested:

```text
1 failed, 4 passed
```

After the implementation:

```text
Backend Skill-version tests: 10 passed
Collection member editor tests: 5 passed
TypeScript typecheck: passed
```

The first code-quality review found that the initial by-ID route shadowed the
valid namespace `by-id`, and that the first degraded-draft guard prevented both
silent loss and legitimate repair. The route/degraded repair tests failed RED:

```text
Backend: 2 failed, 9 passed
Web: 2 failed, 8 passed
```

After moving the ID endpoint to a separate path family, preserving both
numeric and text slugs under the `by-id` namespace, and adding explicit
degraded repair:

```text
Backend: 11 passed
Web: 2 files passed; 10 tests passed
TypeScript typecheck: passed
```

## Real PostgreSQL identity evidence

A disposable PostgreSQL 16 database applied the full bundled and local
migration chain. The fixture used two Skills in the same namespace with the
same slug and version but different immutable IDs and owners:

| Selection | Skill ID | Version ID | Owner |
| --- | ---: | ---: | --- |
| First duplicate coordinate | 201 | 901 | `task4-owner-a` |
| Requested duplicate coordinate | 202 | 902 | `task4-owner-b` |

Replacing the draft with IDs `202` and `902` stored exactly:

```json
{
  "skill_id": 202,
  "skill_version_id": 902,
  "skill_slug_snapshot": "duplicate-coordinate",
  "skill_version_snapshot": "1.0.0",
  "skill_owner_id_snapshot": "task4-owner-b"
}
```

The mismatched pair `202/901` and an exact pair from another namespace
`303/903` both returned:

```json
{
  "status": 400,
  "detail": "error.collection.member.notFound"
}
```

Both rejected writes rolled back. The draft revision remained `2`, and the
stored `202/902` member was unchanged. The exact disposable container and its
anonymous volume were removed after verification.

## Core-regression verification

Focused collection, GitLab import, Skill-version, route-policy, and
architecture coverage:

```text
176 passed, 2 warnings in 37.39s
```

Focused Web collection, repository-import, and Skill hook coverage:

```text
10 files passed; 38 tests passed
```

Complete Web regression:

```text
207 files passed; 747 tests passed
```

Complete Python backend regression:

```text
1088 passed, 2 warnings in 231.35s
```

The two backend warnings are the existing Starlette `TestClient` deprecation
and the intentional duplicate ZIP-name archive fixture warning.

The following gates also passed:

- TypeScript `tsc --noEmit`;
- focused ESLint with zero warnings;
- Python SQL inventory check;
- production Web build (with only the existing runtime-config and bundle-size
  warnings);
- `git diff --check` (only existing line-ending warnings).

## Review disposition

The first independent code-quality review found two Important issues:

- the initial `/api/web/skills/by-id/...` route shadowed the legal `by-id`
  namespace;
- degraded drafts were protected from silent deletion but could not be
  repaired in the maintenance UI.

It also identified duplicated version-list logic as a Minor maintenance risk.
All three findings were corrected. Final independent specification and
code-quality reviews returned `PASS`.

The quality reviewer live-probed all three routes with both readers registered:

| Route | Observed reader |
| --- | --- |
| `/api/web/skill-versions/by-skill-id/202` | ID reader with `202` |
| `/api/web/skills/by-id/202/versions` | coordinate reader with `by-id/202` |
| `/api/web/skills/by-id/demo/versions` | coordinate reader with `by-id/demo` |

Both reviewers independently reran the 11-test backend and 10-test Web
repair gates plus TypeScript typecheck. The specification reviewer also
confirmed the old overlapping endpoint no longer exists. No Important,
Critical, or other actionable Task 4 finding remains.

No commit, stage, push, deployment, feature enablement, or real GitLab/Nexus
operation was performed.

# Orphan Skill Cleanup And Namespace Delete Diagnostics

Date: 2026-07-17
Status: Approved for implementation

## Problem

A skill can remain visible through a stale or incomplete published projection while its detail or
resources cannot be read. Platform administrators also lack a narrow read-only override for
diagnosing inaccessible skills, and namespace deletion exposes no dependency details.

## Goals

1. Exclude published search results whose latest published version has no `skill_file` rows.
2. Let `SUPER_ADMIN`, but not `SKILL_ADMIN`, inspect skill detail, versions, and file metadata across
   visibility and archived-namespace boundaries.
3. Add bounded, explicit resource diagnostics for database metadata and object storage.
4. Reuse the existing audited hard-delete flow for abnormal skills.
5. Return namespace deletion blocker counts and let `SUPER_ADMIN` delete a dependency-free team
   namespace without becoming its owner.

## Boundaries

- Search remains database-only; it never probes MinIO/S3.
- Storage permission or network errors are reported as unverified, not missing objects.
- Platform read override does not grant ordinary lifecycle, review, promotion, or membership actions.
- The global namespace remains immutable.
- Namespace deletion does not cascade-delete review or promotion history.

## Backend Design

Search, index rebuild, and index upsert require a `skill_file` row for the joined latest published
version. Web read routes resolve the optional authenticated principal and pass an explicit
`platform_read_override` flag into detail, version, and file readers. The detail response reports
`platformAdminOverride` separately from `canManageLifecycle`.

`GET /api/v1/admin/skills/{skill_id}/resource-diagnostics` is session/mock `SUPER_ADMIN` only. It
checks version/file metadata, blank storage keys, bundle objects, and up to 500 individual file
objects. Probe failures remain distinguishable from confirmed missing objects.

One shared namespace dependency reader returns skill, review-task, and promotion-request counts.
Managed namespace responses include `deleteAuthorized`, `canDelete`, and `deleteBlockers`; the
delete mutation repeats authorization and blocker checks in its transaction.

## Frontend Design

The skill detail page renders a cleanup section only when `platformAdminOverride` is true, fetches
diagnostics on demand for that view, and reuses typed-slug hard-delete confirmation. The namespace
page shows an authorized but blocked delete command as disabled with exact blocker counts.

## Verification

- Repository tests for search and index file-row boundaries.
- Access tests for users, `SKILL_ADMIN`, and `SUPER_ADMIN`.
- Diagnostic tests for healthy, missing, partial, capped, and unverified outcomes.
- Namespace read/mutation tests for owners, platform administrators, blockers, and global namespace.
- Frontend interaction tests, full backend/frontend suites, typecheck, lint, build, and
  `git diff --check`.

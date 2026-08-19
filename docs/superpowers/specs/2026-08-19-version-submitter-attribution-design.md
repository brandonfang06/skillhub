# Version Submitter Attribution Design

**Date:** 2026-08-19

**Status:** Approved for implementation planning

**Scope:** Skill and version attribution in Skill Detail, including native uploads and OSS source imports

## Problem

Skill ownership and version attribution currently answer different questions but
are easy to confuse:

- `skill.owner_id` identifies the skill container's primary maintainer.
- A version may be submitted by a different user.
- An OSS version is imported by a service principal on behalf of a pipeline
  initiator.

Automatically changing the skill owner whenever another user submits or imports
a version would allow a pipeline rerun to transfer management responsibility.
It would also make notifications, authorization, and the visible maintainer
change as a side effect of routine upstream synchronization.

Users instead need to see who submitted the selected version while the skill's
long-term owner remains stable.

## Decision

Skill ownership remains container-level and does not change when a new version
is submitted or imported. Ownership changes only through an explicit ownership
transfer workflow.

Every visible skill version exposes a version submitter:

- Native SkillHub versions display **Submitted by**.
- OSS source-import versions display **Imported by**.

The Skill Detail page defaults to the latest visible version, so the displayed
person naturally answers "who submitted or imported the latest version?" When
the user selects a historical version, the attribution changes with that
version.

OSS and native skills continue using the same Skill and SkillVersion lifecycle.
OSS import remains an origin/provenance overlay, not a separate catalog entity.

## Domain Language

### Skill Owner

The primary maintainer and contact for the skill container. The owner has
container-level management rights but is not assumed to have submitted every
version. A new version never transfers ownership implicitly.

### Version Submitter

The human SkillHub account whose action submitted a particular version into the
publication and review lifecycle. This is version-scoped attribution and may
differ between versions.

For an OSS import, the version submitter is the resolved pipeline initiator. If
the initiator has no SkillHub identity, the existing namespace OWNER used by the
importer's attribution fallback is the version submitter.

### Import Actor

The service principal authenticated by the `st_` service token. It authorizes
and audits the machine operation but is not presented as the human version
submitter.

### Original Importer

The submitter of the first imported version. This can be derived from version
history and is not a new skill-level ownership field in this scope.

## Alternatives Considered

### 1. Latest Submitter Becomes Skill Owner

Rejected. It turns a routine submission or pipeline rerun into an implicit
ownership transfer and makes responsibility unstable.

### 2. Separate OSS Skill Model

Rejected. A separate OSS catalog entity would duplicate lifecycle, scanner,
review, search, download, and analytics behavior. The meaningful difference is
source provenance and attribution, which can remain a version overlay.

### 3. Stable Owner With Per-Version Submitter

Selected. It preserves current authorization and operational responsibility
while making each contributor's work visible.

## Existing Data And Storage Decision

The first implementation should not add another submitter column or table.
Current records already contain the necessary identities:

- `review_task.submitted_by` records the human review submitter.
- `skill_version.created_by` is available as a compatibility fallback for a
  version without a review task.
- `local_oss_skill_version_source.imported_by` records the attributed human for
  each OSS version.
- `local_oss_skill_version_source.imported_by_service_principal_id` records the
  machine actor separately.

The read model resolves attribution in this order:

1. For an OSS source version, use `local_oss_skill_version_source.imported_by`
   and `imported_at`.
2. Otherwise, use the review task associated with that version. If more than
   one historical review exists, use the task whose approval produced the
   visible version; for an active pending or rejected preview, use the latest
   applicable submission.
3. If no review task exists, fall back to `skill_version.created_by` and
   `skill_version.created_at`.

The implementation plan must first prove these joins against real PostgreSQL.
If an existing lifecycle path cannot resolve a submitter deterministically, the
plan must stop and propose a schema migration rather than silently choosing an
arbitrary review row.

## API Contract

`SkillVersionDetail` gains a common nullable attribution object:

```json
{
  "versionAttribution": {
    "type": "OSS_IMPORT",
    "submittedBy": "user-id",
    "submittedByName": "hcfange",
    "submittedAt": "2026-08-19T08:00:00Z"
  }
}
```

Contract rules:

- `type` is `NATIVE_SUBMISSION` or `OSS_IMPORT`.
- `submittedBy` is the stable SkillHub user ID.
- `submittedByName` is the current user-facing display name. If unavailable,
  the frontend falls back to `submittedBy`.
- `submittedAt` is the applicable review submission time or OSS import time.
- Native versions without resolvable attribution return
  `versionAttribution: null`; the API does not invent a user.
- `sourceProvenance` remains the source repository, revision, ref, path,
  fingerprint, and browse-link contract. It does not become an authorization
  model.

The generated OpenAPI types must be regenerated; generated files are never
edited manually.

## Skill Detail UI

For the currently selected version:

- Native version metadata displays `Submitted by <display name>` and the
  submission time.
- The existing Source Provenance card displays `Imported by <display name>` and
  the import time alongside repository revision and source path.
- The skill owner remains visible in its existing container-level location and
  is not relabeled as the version submitter.
- Changing the selected version updates attribution together with provenance.
- Long display names wrap without hiding the source link or other metadata.
- English, Simplified Chinese, and Traditional Chinese translations are
  required.

No personal OAuth token, preferred username, or service-token secret is exposed
by this UI. The public display uses the same user-facing name policy as other
SkillHub user attribution surfaces.

## Data Flow

1. A native user submission or OSS pipeline creates a version and its review
   attribution using the existing write path.
2. OSS import also persists source provenance, human `imported_by`, and the
   service-principal actor.
3. The version-detail repository reads the selected version and resolves its
   common attribution deterministically.
4. The version-detail API returns `versionAttribution` and, for OSS versions,
   `sourceProvenance`.
5. Skill Detail renders the label based on attribution type.

## Error And Historical-Data Behavior

- A deleted or disabled submitter does not erase historical attribution. The
  API keeps the stored user ID and returns the available display name.
- A missing current user row results in an ID fallback where the database
  relationship permits it; it never transfers attribution to the skill owner.
- Older native versions without a resolvable submitter show no submitter row.
- Missing OSS provenance is treated as a data-integrity problem in tests and
  diagnostics, not rewritten to a native submission.
- Identity resolution failures during a new OSS import keep the existing
  importer behavior: missing initiator falls back to the current namespace
  OWNER; ambiguous or inactive identities fail the import.

## Verification

Backend tests must cover:

- native submitted version attribution;
- OSS `imported_by` attribution and separate service actor;
- latest and historical version selection;
- skill owner remaining unchanged across submissions by different users;
- native compatibility fallback and unresolved historical data;
- display-name lookup without exposing OAuth login data;
- root and `/skillhub` API behavior.

Frontend tests must cover:

- `Submitted by` for native versions;
- `Imported by` inside Source Provenance for OSS versions;
- version switching updates the person and timestamp;
- owner and submitter are displayed as distinct concepts;
- long names and all three locales.

End-to-end acceptance must use the complete local runtime with PostgreSQL,
Redis, MinIO, scanner, backend, root web, and `/skillhub` web. It must submit or
import two versions under different users, approve them through the normal
review lifecycle, and confirm that the skill owner stays fixed while the
selected version shows the correct submitter.

## Non-Goals

- Automatic or implicit skill ownership transfer.
- A separate OSS skill or catalog lifecycle.
- Skill maintainer/collaborator roles.
- Changing namespace ownership.
- Bypassing scanner or namespace-owner review.
- Displaying the service principal as the human contributor.
- Reworking existing source repository naming, GitLab variables, or service
  token authorization.

---
name: skill-lifecycle
description: The authoritative skill lifecycle state model including container states, version states, review workflow states, visibility overlay, and governance actions. Ensures agents don't introduce invalid states or transitions.
license: Apache-2.0
---

# Skill Lifecycle Skill

## Trigger

Use this skill when:

- modifying publish, review, withdrawal, or unpublish flows;
- changing skill, version, review, or visibility state;
- projecting lifecycle state in search, detail, or listing responses;
- implementing archive, hide, yank, or delete operations;
- adding transition authorization or transaction behavior.

## Current Sources Of Truth

Read the implementation and its focused tests before changing a transition:

- transport routes: `server-python/app/api/publish.py`,
  `server-python/app/api/lifecycle.py`, and
  `server-python/app/api/reviews.py`;
- publish workflow: `server-python/app/publish/`;
- lifecycle mutations: `server-python/app/lifecycle/skill.py` and
  `server-python/app/lifecycle/hard_delete.py`;
- review workflow: `server-python/app/review/approval.py`;
- public and owner projections: `server-python/app/skills/read_repository.py`
  and `server-python/app/skills/read_access.py`;
- regression coverage: `server-python/tests/test_skill_lifecycle_*.py`,
  `server-python/tests/test_publish_*.py`, and
  `server-python/tests/test_review_*.py`.

Keep route handlers transport-only. Put SQL and transactional state changes in
the focused workflow, repository, or helper modules above.

## State Model

### Skill Container

| State | Meaning |
| --- | --- |
| `ACTIVE` | The skill can participate in normal publish and read workflows. |
| `ARCHIVED` | Owner-managed retirement state; new publish actions are blocked. |

Platform hiding is the independent `hidden` boolean overlay. Do not add a
second lifecycle state for hiding.

### Skill Version

| State | Meaning |
| --- | --- |
| `DRAFT` | Editable non-public version. |
| `SCANNING` | Security scan is in progress. |
| `SCAN_FAILED` | Security scan failed. |
| `UPLOADED` | Uploaded without an active review task, including private versions and withdrawn submissions. |
| `PENDING_REVIEW` | Frozen pending a review decision. |
| `PUBLISHED` | Distributable version. |
| `REJECTED` | Retained rejected submission. |
| `YANKED` | Previously published version removed from distribution. |

### Review Task

| State | Meaning |
| --- | --- |
| `PENDING` | Awaiting a reviewer. |
| `APPROVED` | Review approved. |
| `REJECTED` | Review rejected. |

### Visibility

| Value | Publish behavior |
| --- | --- |
| `PUBLIC` | Normal publish creates a reviewable version; authorized platform auto-publish can publish directly. |
| `NAMESPACE_ONLY` | Uses the review flow but limits read scope to the namespace. |
| `PRIVATE` | Goes to `UPLOADED` without a review task. |

## Core Transitions

| Action | From | To |
| --- | --- | --- |
| Public or namespace upload | new version | `PENDING_REVIEW` |
| Authorized auto-publish | new version | `PUBLISHED` |
| Private upload | new version | `UPLOADED` |
| Approve review | `PENDING_REVIEW` | `PUBLISHED` |
| Reject review | `PENDING_REVIEW` | `REJECTED` |
| Withdraw review | `PENDING_REVIEW` | `UPLOADED` |
| Yank | `PUBLISHED` | `YANKED` |
| Archive | `ACTIVE` | `ARCHIVED` |
| Unarchive | `ARCHIVED` | `ACTIVE` |

Publishing a replacement auto-withdraws an existing pending version before the
new publish transaction proceeds. Preserve this behavior and its review-task
cleanup.

## Latest Pointer And Read Projection

`skill.latest_version_id` is a workflow pointer, not proof that a version is
public:

- direct `PUBLISHED` versions update it;
- private `UPLOADED` versions also update it for owner/private workflows;
- public resolution, browsing, install, download, and search still require a
  `PUBLISHED` version and apply visibility/access checks;
- when deletion or yank invalidates the pointer, recalculate from remaining
  published versions using publish time, creation time, then id ordering.

Read models may expose a published version and a separate owner preview.
Never let a pending, rejected, private-only, or yanked version leak into public
resolution merely because it is newest or referenced by the pointer.

## Mutation Boundaries

- Submit review only from `UPLOADED` or `DRAFT`, and only for `PUBLIC` or
  `NAMESPACE_ONLY`.
- Withdraw review only while both the version and review task are pending, and
  only for the original submitter.
- Delete a version only from `DRAFT`, `REJECTED`, `SCAN_FAILED`, or `UPLOADED`.
- Do not delete the last remaining version through the ordinary version-delete
  flow.
- Archive and unarchive require owner or namespace-manager authorization.
- Review decisions require the current platform or namespace review role and
  must prevent invalid self-review.
- Administrative hide, restore, yank, and hard-delete routes must enforce their
  route-specific platform authorization before calling mutation code.

Mutations must keep authorization, audit actor, idempotency, transaction, and
rollback or compensation behavior together. Storage cleanup occurs only after
the database transaction establishes the durable deletion state.

## Verification

Run the smallest focused lifecycle, publish, and review tests first. For a
broad state-model change, run:

```powershell
cd server-python
uv run pytest tests/test_skill_lifecycle_*.py tests/test_publish_*.py tests/test_review_*.py -q
```

Also verify the affected HTTP route and read projection end-to-end. Passing
mutation tests alone does not prove that public and owner views expose the
correct version.

## Common Pitfalls

- treating `hidden` as a container state instead of an overlay;
- treating `latest_version_id` as automatically public;
- forgetting pointer recalculation after yank or deletion;
- leaving a pending review task when replacing or withdrawing a version;
- skipping the explicit warning-confirmation step in publish flows;
- adding SQL or lifecycle orchestration directly to route handlers.

# Download Events Human-Readable User Filter Design

**Date:** 2026-08-10

**Status:** Approved for implementation

**Scope:** Platform-admin Download Events list and CSV export

## Problem

The Download Events page exposes an exact `userId` filter and renders the
opaque user ID as the primary identity. OAuth users already have a readable
identity stored in `user_account.display_name`, but administrators cannot use
that value to find events and must interpret internal IDs.

For generic OIDC providers, SkillHub derives the stored display name from
`preferred_username`, then `name`, email, login, username, subject. GitHub and
GitLab use their provider login. This feature therefore does not require a new
OAuth claim mapping, environment variable, or schema migration.

## Goals

- Let a platform administrator search download events with a readable display
  name or a user ID from one input.
- Show the readable display name as the primary identity and retain the stable
  user ID as secondary audit evidence.
- Apply identical user filtering to the paginated admin list and CSV export.
- Preserve the existing exact `userId` API filter for callers and saved links.
- Keep root and `/skillhub` deployments working without hard-coded prefixes.

## API Contract

`GET /api/v1/admin/download-events` and
`GET /api/v1/admin/download-events.csv` gain the optional query parameter:

```text
userQuery=<display-name-or-user-id-fragment>
```

`userQuery` is trimmed and matched case-insensitively as a substring against:

- `user_account.display_name`; or
- `local_skill_download_event.user_id`.

PostgreSQL `LIKE` metacharacters (`%` and `_`) are escaped so the input keeps
literal substring semantics.

If `userId` is supplied, its existing trimmed exact-match behavior remains.
If both parameters are supplied, both filters apply. The user-facing page sends
`userQuery`; direct API callers can continue using `userId`.

The existing response and CSV identity fields remain unchanged for
compatibility:

- `username` contains `user_account.display_name`;
- `userId` contains the stable SkillHub identity.

The skill-scoped analytics endpoint remains unchanged because this request is
for the platform-admin investigation page.

## Query Design

SQL remains in `server-python/app/download_analytics/repository.py`. The admin
count, row, and CSV queries use the same `LEFT JOIN user_account` and shared
where-clause builder so totals and rows cannot disagree. Values remain bound
SQL parameters.

Display-name matches may return multiple users. This is intentional: rows show
their user IDs so administrators can distinguish same-name accounts. Anonymous
events have no user identity and do not match a non-empty user query.

## Frontend Behavior

- Replace the User ID input wording with "User name or ID".
- Accept `userQuery` in validated route search state.
- Continue accepting legacy `userId` route state as the initial input value;
  once rendered, the page uses the new combined query behavior.
- Build list and CSV URLs with `userQuery` and the configured API base path.
- Render `username` first. Render `userId` beneath it in subdued monospace
  text when a display name exists. If no display name exists, render the ID as
  the primary value. Keep the localized anonymous label for anonymous events.
- Update English, Traditional Chinese, and Simplified Chinese translations.

## Verification

Automated coverage must prove:

- repository display-name and user-ID substring matching, case insensitivity,
  same-name results, exact `userId` compatibility, and matching list/CSV
  filters;
- route binding and generated OpenAPI exposure of `userQuery`;
- frontend search parsing, API and CSV URL construction, readable identity
  ordering, translations, and legacy route initialization;
- full backend tests, frontend tests, typecheck, lint, and production build.

Runtime verification must start PostgreSQL, Redis, MinIO, scanner, FastAPI, and
web, apply Python migrations, seed OAuth-like users and download events in real
PostgreSQL, and verify the changed path through the browser/API. Repeat the
browser flow for root and canonical `/skillhub` routing using the production
web/Nginx path.

## Non-Goals

- No user autocomplete or identity-picker endpoint.
- No OAuth claim-mapping change.
- No database migration or denormalized display-name snapshot on events.
- No email search or exposure of new personal information.
- No change to download recording, retention, authorization, scanner, CLI, or
  deployment manifests.
- No commit, merge, push, or pull request in this implementation session.

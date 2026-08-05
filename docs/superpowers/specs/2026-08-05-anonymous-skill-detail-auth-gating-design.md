# Anonymous Skill Detail Authentication Gating Design

**Status:** Approved and verified on the feature branch; pending merge
**Date:** 2026-08-05

## Problem

A public Skill Detail route currently mixes public metadata with content that
requires an authenticated session. An anonymous visitor can load the skill and
version metadata, but the README and individual file bodies call protected file
content endpoints. Those requests return `401`; the frontend text-fetch helper
then loses the structured HTTP error, and the global query error handler shows
the generic `Operation failed` notification.

The resulting experience incorrectly looks like a broken public page. Public
skill discovery should remain useful without signing in, while protected skill
content and account-specific actions must keep their existing authorization
boundary.

## Existing Product And Security Baseline

- The logical route `/space/$namespace/$slug` is intentionally public.
- Public skill detail, version metadata, and version file listings can be read
  anonymously when the skill visibility rules allow it.
- README and individual file bodies use the protected version-file content
  endpoint and require a current user.
- The backend has explicit tests for the `401` file-content contract. This is
  an intentional security boundary, not an environment-dependent failure.
- The Skill Detail page already has a `requireLogin` navigation path that sends
  the user to the logical `/login` route with a `returnTo` target.
- The shared JSON fetch path preserves structured API errors, but the text fetch
  path currently throws a plain error and loses the response status.
- SkillHub supports both root deployment and the canonical `/skillhub` browser
  base path. Application routes must remain logical, and browser-visible URLs
  must use the shared router and base-path contract.

## Goals

- Keep the basic information for an anonymously readable public skill visible.
- Do not request protected README or file-body content before authentication.
- Replace the generic failure experience with clear inline login affordances.
- Preserve the exact Skill Detail destination across login.
- Keep authenticated Skill Detail behavior and backend permissions unchanged.
- Distinguish an expected authentication requirement from an unexpected server
  or data failure.

## Considered Approaches

### 1. Authentication-aware page gating (selected)

Resolve the current-user state before enabling protected content queries. Render
an inline locked state for anonymous visitors, and initiate login only after an
explicit click. Preserve HTTP status in the text-fetch layer so a session that
expires after initial load can also be handled accurately.

This prevents the expected `401` instead of reacting to it, keeps the public
route useful, and makes the smallest change consistent with the backend access
contract.

### 2. Redirect every `401` globally

Let protected requests fail and make the global error handler immediately send
the browser to login. This is mechanically simple, but it causes surprise
navigation during anonymous browsing, conflates an expected login boundary with
a broken session, and cannot provide the approved inline README state.

### 3. Allow anonymous file-content reads in the backend

Expose README and file bodies whenever the skill container is publicly visible.
This would remove the frontend `401`, but it changes an intentional security
contract and broadens anonymous data exposure. It is outside the requested UX
repair and is rejected.

## User Experience

### Public information

An anonymous visitor can continue to see all information allowed by the current
public-detail contract, including the skill name, summary, namespace, visibility
and lifecycle metadata, version information, and public counts.

Public metadata does not wait for the current-user query. The protected content
area must not briefly render a locked state while that query is still loading;
it uses a neutral loading treatment until authentication state is known, then
renders either protected content or the anonymous state.

### README tab

For an anonymous visitor:

- do not send the README content request;
- render a locked card in the README area;
- explain that sign-in is required to view the README;
- provide a primary `Sign in to view` action;
- do not show a toast, modal, or automatic redirect.

Clicking the action navigates to the logical `/login` route and includes the
current Skill Detail location as `returnTo`.

For an authenticated visitor, README loading and rendering remain unchanged.

### Files tab

An anonymous visitor can see the public file listing and filenames. The Files
area displays a short `Sign in to preview file contents` notice. Clicking a
file initiates login with the same `returnTo` behavior instead of opening the
preview or sending a file-content request.

An authenticated visitor can open and switch file previews as before.

### Login-required actions

Star, subscription, rating, report, playground, and other account-specific
controls remain discoverable when their existing page rules make them visible.
For an anonymous visitor, clicking one uses the common login navigation rather
than first sending a request that is expected to return `401`.

Existing anonymous download policy is not changed. A download that the current
backend and UI allow anonymously remains available; a download that requires a
session uses the same explicit login path.

## Frontend Design

### Page-level authorization decision

The Skill Detail page owns the presentation decision because it already
coordinates the selected version, README, file tree, preview, and action
controls. It consumes the existing current-user state and derives whether
protected content queries may run.

The README and file-content query hooks accept an authentication-aware enabled
condition. Public detail, versions, and file-listing queries remain independent
of this condition. This keeps the backend-data boundaries explicit:

```text
Anonymous public route
  -> public skill detail, versions, file listing
  -> inline lock for README and file bodies
  -> login only after an explicit action

Authenticated public route
  -> public skill detail, versions, file listing
  -> protected README and selected file body
```

The locked presentation should remain local to the Skill Detail feature unless
an existing focused component already matches it. Do not introduce a generic
authorization component hierarchy for one page.

### Error fidelity

Align the shared text-fetch behavior with the JSON fetch behavior by preserving
HTTP status and response detail in the existing structured API error type. Audit
its callers and cover the change with focused tests; do not alter response-body
rendering or successful text semantics.

Mark the README and file-content queries as locally handled so their expected
authentication errors do not also trigger the global query error notification.
The page handles errors as follows:

- known anonymous state: the protected query never runs;
- `401` after a previously authenticated state: replace the affected content
  area with a session-expired login card and preserve `returnTo`;
- `403`, `404`, and unexpected failures: retain an explicit content error state
  with the existing retry behavior where applicable;
- public skill-detail failure: retain the page-level not-found, forbidden, or
  general failure behavior rather than converting it into a content lock.

This feature does not rewrite the application-wide `401` policy. Only queries
whose errors are deliberately rendered inside Skill Detail bypass the global
notification path.

### Navigation and subpath compatibility

All navigation uses TanStack Router application routes and the existing shared
`returnTo` helper. Do not hard-code `/skillhub`, concatenate browser-root login
URLs, or create a second base-path implementation.

The same behavior must work at both:

```text
/space/{namespace}/{slug}
/skillhub/space/{namespace}/{slug}
```

The public browser URL after login must return to the same skill, selected
query parameters, and fragment when those values are safe and supported by the
existing return-target contract.

## Backend And API Contract

No backend route, authorization rule, response schema, database schema, or
environment variable is required for this feature.

In particular:

- file-content endpoints continue to require authentication;
- public skill metadata and public file-listing behavior remain unchanged;
- the frontend avoids requests it already knows cannot succeed anonymously;
- backend `401`, `403`, and `404` meanings remain authoritative.

If implementation discovers that an existing frontend-generated type is
insufficient, prefer a frontend-local state type. Do not change OpenAPI merely
to represent a view-only locked state.

## Accessibility And Content

- The lock card uses semantic text and a real button or link with a visible
  focus state.
- The lock icon, if present, is decorative unless it conveys information not
  already stated in text.
- Keyboard activation follows the same login path as pointer activation.
- Loading, locked, session-expired, and failed states have distinct text.
- Add English, Simplified Chinese, and Traditional Chinese messages through the
  existing localization structure; do not inline user-facing strings.

## Verification Design

Develop test-first at the affected page, query, and transport seams.

### Frontend tests

- Anonymous public detail renders its public metadata and the README lock card.
- The README content query is disabled while anonymous.
- The login action includes the exact safe Skill Detail `returnTo` target.
- Files remain listed anonymously, but clicking one does not request its body
  and instead initiates login.
- Account-specific controls do not send protected mutations before anonymous
  login navigation.
- Authenticated users still load and render README and selected file bodies.
- An authenticated content request that returns `401` renders the session-
  expired state without the generic global `Operation failed` notification.
- Other content failures retain an explicit error/retry state.
- The text-fetch helper preserves structured status and error information for
  unsuccessful responses while leaving successful text unchanged.
- Localization keys render in English, Simplified Chinese, and Traditional
  Chinese.

Run focused frontend tests, then the complete frontend test, typecheck, lint,
and production-build gates.

### Full runtime verification

Start the complete local release topology used by this workspace, including
PostgreSQL, Redis, MinIO, scanner, Python backend, web, and the subpath proxy.
Do not claim end-to-end verification from mocked UI tests or a frontend-only
development server.

Through the production bundle at `/skillhub`, verify in a real browser that:

- an anonymous deep link to a public skill stays on Skill Detail;
- public metadata and the file tree render;
- README shows the lock card;
- initial load sends no protected README or file-body request;
- no `Operation failed` notification appears and the console/network panel has
  no feature-generated `401`;
- clicking the README action, a filename, and representative account-specific
  controls reaches the base-path-aware login URL with the correct `returnTo`;
- successful login returns to the same Skill Detail page;
- an authenticated visitor can read the README and preview files;
- direct reloads and browser back/forward navigation preserve `/skillhub`.

Repeat the core route and login-target assertions for a root-path deployment or
the existing automated root-path configuration. Record exact commands, service
health, test counts, and browser observations before completion.

## Success Criteria

- Anonymous visitors can understand the public skill without encountering a
  generic failure.
- No protected README or file-body request is made merely by opening the public
  page anonymously.
- Every login-required surface provides an intentional login path that returns
  to the skill.
- Backend permissions and anonymous download semantics do not change.
- Root and `/skillhub` deployments both pass automated and full-runtime checks.

## Non-Goals

- No anonymous access to README or individual file bodies.
- No backend authorization relaxation or new public-content endpoint.
- No database migration, schema change, or environment-variable dependency.
- No redesign of the complete Skill Detail page or its public information
  hierarchy.
- No application-wide rewrite of authentication, query errors, or toast policy.
- No modal login prompt or automatic redirect on anonymous page load.
- No changes to skill lifecycle, visibility, publishing, or download policy.
- No Java, Maven, Spring Boot, or hybrid backend work.

## Decisions

- 2026-08-05: Keep public skill basic information visible and gate only content
  and operations that require authentication.
- 2026-08-05: Show an inline locked README card with a `Sign in to view` action;
  do not show a toast, modal, or automatic redirect.
- 2026-08-05: Keep the public file tree visible, but require login before file
  preview and do not send anonymous file-body requests.
- 2026-08-05: Use page-level authentication-aware query gating rather than a
  global `401` redirect or a backend permission change.
- 2026-08-05: Preserve structured errors for text responses and locally handle
  protected-content failures so expected authentication boundaries do not
  become generic notifications.
- 2026-08-05: Preserve the shared root/subpath navigation contract and verify
  the feature through the complete PostgreSQL-backed local runtime.
- 2026-08-05: The user delegated remaining interaction details to the selected
  recommended design.

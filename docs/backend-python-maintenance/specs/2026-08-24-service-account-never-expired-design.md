# Service Account Never-Expired Token Design

Date: 2026-08-24

Status: implemented and verified

## Context

The Service Accounts page on current `dev` rendered the untranslated keys
`common.cancel` and `common.create`. The prior translation, long-name, and
three-year-expiry work existed only on
`codex/service-account-ui-expiry-polish`; it was never merged into `dev`.

Platform administrators also need an explicit option to create and rotate a
service token that does not expire. This is intended for automation where a
fixed service credential is operationally preferable, while revocation and
principal disablement remain the emergency controls.

## Decisions

### Explicit nullable expiry contract

- `expiresAt` remains a required request property for create and rotate.
- Its value is `string | null` in the HTTP contract.
- A timestamp creates an expiring token; `null` creates a never-expiring token.
- Omitting the property remains invalid so a client bug cannot silently create
  a permanent credential.
- Responses expose `expiresAt: string | null`.

### Security and lifecycle

- Only the existing `SUPER_ADMIN` Service Accounts routes may create or rotate
  these tokens.
- Never-expiring is not the UI default. The default remains 90 days.
- The UI requires an explicit Never Expires selection and displays that the
  token remains valid until revoked or the service principal is disabled.
- Existing scope, hashing, one-time secret display, audit actor, rotation,
  revocation, and principal-disable behavior are unchanged.
- Authentication treats a token as time-valid when `expires_at IS NULL` or the
  timestamp is in the future.

### Expiring-token behavior

- Preserve the previously approved maximum of three calendar years.
- The frontend displays the current maximum and rejects invalid dates before
  submission.
- The backend enforces the same calendar-date boundary.
- February 29 maps to February 28 in the third non-leap year.

### Schema and read models

- Add a Python-owned local migration that drops `NOT NULL` from
  `service_token.expires_at`.
- Do not rewrite the original service-principal migration.
- Active-token counts include unrevoked never-expiring tokens.
- Nearest expiry remains the minimum timestamp among active expiring tokens;
  it is `null` when no active expiring token exists.

### UI and translations

- Use existing `dialog.cancel` for Cancel and
  `servicePrincipals.create` for Create Service Principal.
- Support English, Simplified Chinese, and Traditional Chinese for every new
  label, warning, validation message, and Never Expires display value.
- Restore the full-width token-name input and readable long-name rows without
  hiding rotate/revoke actions.
- A never-expiring token row displays the localized Never Expires label.

## Verification seams

1. Page DOM: the create dialog never renders a raw `common.*` action key.
2. HTTP/OpenAPI: create and rotate require `expiresAt` but accept explicit
   `null`, and responses return `null`.
3. Domain: expiring tokens enforce the three-calendar-year boundary; null
   expiry is preserved.
4. PostgreSQL/auth: the migration permits null, create/rotate persist it, and a
   never-expiring token authenticates until revoked or its principal is
   disabled.
5. Browser: a real Platform Admin can select Never Expires, create a token,
   see it listed correctly, and use the translated dialog at root and
   `/skillhub` deployments.

## Documentation

- Update the Chinese GitLab OSS source-import SOP with both the three-year
  maximum and explicit Never Expires option.
- State that permanent service tokens require an operator-owned rotation and
  revocation procedure.
- No new environment variables are required.

## Non-goals

- Do not change personal API-token expiry behavior.
- Do not make Never Expires the default.
- Do not add token scopes or change source-import authorization.
- Do not alter existing token expiry values.
- Do not reintroduce Java, Maven, Spring Boot, or a hybrid runtime.

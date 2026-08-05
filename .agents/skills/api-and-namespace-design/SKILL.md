---
name: api-and-namespace-design
description: API design conventions, namespace coordinates, RBAC, ClawHub compatibility, OpenAPI synchronization, and session/CSRF handling for the Python backend.
license: Apache-2.0
---

# API And Namespace Design Skill

## Trigger

Use this skill when changing REST endpoints, namespace or skill coordinates,
RBAC, ClawHub compatibility, auth transport, or OpenAPI contracts.

## Namespace Coordinates

SkillHub coordinates use:

```text
@{namespace_slug}/{skill_slug}
```

- `@global/my-skill` is a global skill.
- `@my-team/my-skill` is owned by the `my-team` namespace.
- Namespace roles are `OWNER`, `ADMIN`, and `MEMBER`.
- Platform `SUPER_ADMIN` policy is separate from namespace membership.
- Frozen or archived namespaces cannot publish.

Do not assume namespace slugs have a special prefix beyond the coordinate `@`.

## ClawHub Compatibility

ClawHub uses one slug segment:

| SkillHub coordinate | Compatibility slug |
| --- | --- |
| `@global/my-skill` | `my-skill` |
| `@team-name/my-skill` | `team-name--my-skill` |

The double-dash split takes priority, so global skill slugs must not contain
`--`.

`/.well-known/clawhub.json` advertises the API base under the configured web
base path. Root deployments return `{"apiBase":"/api/v1"}`. With
`SKILLHUB_WEB_BASE_PATH=/skillhub`, it returns
`{"apiBase":"/skillhub/api/v1"}`.

## FastAPI Boundaries

- Route handlers live in `server-python/app/api/` and remain transport-focused.
- Bind requests, resolve auth context, call a feature workflow or repository,
  and shape the response at the route boundary.
- Business rules live in the matching package under `server-python/app/`.
- SQL belongs in repository, query, or helper modules.
- User identities are strings in API inputs and outputs.
- Reuse the established response envelope and request-id behavior.

## Session And CSRF

- Browser auth uses session cookies.
- Mutating browser requests send the `XSRF-TOKEN` cookie value in the
  `X-XSRF-TOKEN` header.
- Local mock auth uses `X-Mock-User-Id`.
- Protected route tests must cover unauthenticated, unauthorized, and allowed
  behavior.

## OpenAPI Contract Sync

After an API contract change:

```powershell
make generate-api
```

Commit the updated `web/src/api/generated/schema.d.ts`. Do not edit generated
types manually.

Use `scripts/check-openapi-generated.sh` when validating contract drift.

## Key Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/auth/me` | Current user |
| `POST` | `/api/v1/auth/local/login` | Local login |
| `POST` | `/api/v1/auth/local/register` | Local registration |
| `POST` | `/api/v1/auth/logout` | Logout |
| `GET` | `/api/v1/namespaces` | List namespaces |
| `GET` | `/api/v1/labels` | List visible labels |
| `GET` | `/api/v1/health` | Backend health |
| `GET` | `/api/v1/metrics/prometheus` | Prometheus metrics |

## Common Pitfalls

- Missing CSRF headers on cookie-authenticated writes.
- Numeric user IDs.
- Business logic or SQL in route handlers.
- API changes without regenerated frontend types.
- Treating compatibility slugs as native namespace coordinates.

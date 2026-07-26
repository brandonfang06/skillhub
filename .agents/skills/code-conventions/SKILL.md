---
name: code-conventions
description: Code style, logging, and testing conventions for the SkillHub Python backend and TypeScript frontend.
license: Apache-2.0
---

# Code Conventions Skill

## Python Backend

### Types And Boundaries

- Target Python 3.12 and add type hints to public functions.
- Keep FastAPI route handlers transport-focused.
- Put business workflows in the matching feature package under
  `server-python/app/`.
- Put SQL in repository, query, or helper modules.
- Use the existing database session and unit-of-work helpers.
- Keep user IDs as strings.

### Errors And Responses

- Reuse the existing response envelope and request-id helpers.
- Validate external inputs at HTTP, file, environment, and service boundaries.
- Preserve the established HTTP status and error-detail contract.
- Do not catch exceptions only to log and re-raise without adding context.

### Async And Transactions

- Await async database, storage, scanner, Redis, and HTTP operations.
- Do not perform blocking network or filesystem work on the event loop.
- Keep write transactions explicit and test rollback or compensation paths.
- Mutating workflows must preserve authorization, audit actor, and idempotency
  behavior.

### Logging

- Use Python `logging` with parameterized messages.
- Include request, actor, namespace, or skill context when it is available and
  safe to log.
- Never log credentials, tokens, session cookies, or private skill contents.

## TypeScript Frontend

### Type Safety And Data

- Use strict TypeScript and avoid `any`.
- Use generated OpenAPI types from `web/src/api/generated/schema.d.ts`.
- Use TanStack Query for server state; do not fetch server data with
  `useEffect`.
- Use the shared API client and existing query-key conventions.

### Feature Structure

| Layer | Path | Purpose |
| --- | --- | --- |
| Pages | `web/src/pages/` | Route-level composition |
| Features | `web/src/features/` | User workflows |
| Entities | `web/src/entities/` | Domain display logic |
| Shared | `web/src/shared/` | Reusable UI and utilities |

Place code at the lowest appropriate layer. Keep page logic out of `shared`.

### UI Conventions

- Reuse existing Radix primitives and component patterns.
- Use `cn()` for conditional class merging.
- Keep user-facing text in i18next translation resources.
- Test behavior and user interactions, not implementation details.

## Testing

### Backend

- Tests live in `server-python/tests/` and use pytest.
- Write tests before or alongside behavior changes.
- Route changes need response, auth, and request-id coverage.
- Write workflows need transaction, audit, idempotency, and side-effect
  coverage.

```powershell
cd server-python
uv run pytest tests -q
```

### Frontend

- Vitest covers unit and component behavior.
- Playwright covers authenticated browser and viewport flows.

```powershell
cd web
pnpm run typecheck
pnpm run lint
pnpm run test
```

## Common Pitfalls

- Adding SQL to a route instead of a repository boundary.
- Changing an API contract without regenerating frontend types.
- Using numeric user IDs.
- Adding a write path without rollback or compensation coverage.
- Placing feature-specific frontend logic in `shared`.

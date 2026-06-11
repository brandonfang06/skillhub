# Admin Search Bearer Policy Migration Plan

## Summary

Close the API-token route-policy gap for the already Python-owned admin search rebuild route:

- `POST /api/v1/admin/search/rebuild`

This milestone does not move route ownership. It aligns Python behavior with Java's
`RouteSecurityPolicyRegistry`: bearer API tokens are unsupported on admin routes unless a specific
API-token policy allows them.

## Scope

Python-owned route after this milestone:

- `POST /api/v1/admin/search/rebuild`

Behavior:

- no auth remains `401 error.auth.required`;
- `X-Mock-User-Id` remains the supported local development/admin auth path;
- valid bearer API-token principals without a mock user return `403` with
  `API token cannot access endpoint: /api/v1/admin/search/rebuild`;
- invalid bearer tokens remain `401 error.auth.required`;
- if both mock user and bearer token are present, mock-user precedence remains.

Out of scope:

- global middleware for every route;
- OAuth/session behavior;
- Java `server/` edits;
- admin search rebuild data/indexing behavior changes.

## Verification

- Add route tests for valid bearer unsupported, invalid bearer, and mock-user precedence.
- Run:
  - `uv run pytest tests/test_admin_search_rebuild.py tests/test_route_registry.py -q`
  - `npm.cmd run test -- vite.config.test.ts`
  - hybrid live smoke if route behavior changed at the proxy/auth boundary.


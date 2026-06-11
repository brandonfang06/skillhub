# Admin Label Bearer Policy Migration Result

## Summary

Aligned the already Python-owned admin label definition routes with Java API-token route policy:

- `GET /api/v1/admin/labels`
- `POST /api/v1/admin/labels`
- `PUT /api/v1/admin/labels/{slug}`
- `DELETE /api/v1/admin/labels/{slug}`
- `PUT /api/v1/admin/labels/sort-order`

Valid bearer API-token principals without a mock user now receive Java-compatible unsupported
admin-route behavior. The supported local route identity remains `X-Mock-User-Id`.

## Behavior

- Missing auth: `401 error.auth.required`
- Invalid bearer token: `401 error.auth.required`
- Valid bearer API token: `403 API token cannot access endpoint: <path>`
- Mock user plus bearer token: mock-user precedence
- Super-admin mock user: label definition behavior unchanged

## Verification

- `uv run pytest tests/test_admin_label_definitions.py -q`
  - Result: `5 passed, 1 warning`
- `uv run pytest tests/test_admin_label_definitions.py tests/test_route_registry.py -q`
  - Result: `7 passed, 1 warning`
- `npm.cmd run test -- vite.config.test.ts`
  - Result: `47 passed`
- Manual hybrid live gate:
  - Created a Java API token with `skill:read`, `skill:publish`, `skill:delete`, and
    `token:manage` scopes.
  - Java direct `GET /api/v1/admin/labels` with bearer token: `403`
  - Python direct `GET /api/v1/admin/labels` with bearer token: `403`
  - Vite proxy `GET /api/v1/admin/labels` with bearer token: `403`
  - Python invalid bearer token: `401 error.auth.required`
  - Python mock user plus bearer token: `200`

## Follow-Up

This continues the admin-route bearer unsupported cleanup. Remaining Python-owned admin route groups
should receive the same Java-compatible unsupported handling before final proxy cleanup.

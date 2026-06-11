# Admin Label Bearer Policy Migration Plan

## Summary

Close the Java API-token route-policy gap for the already Python-owned admin label definition
routes:

- `GET /api/v1/admin/labels`
- `POST /api/v1/admin/labels`
- `PUT /api/v1/admin/labels/{slug}`
- `DELETE /api/v1/admin/labels/{slug}`
- `PUT /api/v1/admin/labels/sort-order`

Java's `RouteSecurityPolicyRegistry` does not allow bearer API-token access to
`/api/v1/admin/**` unless a specific API-token policy exists. These admin label routes have no
such allow rule, so valid bearer API-token principals must receive Java-compatible unsupported
endpoint `403` responses.

## Scope

Behavior after this milestone:

- missing auth remains `401 error.auth.required`;
- invalid bearer token remains `401 error.auth.required`;
- valid bearer API-token principals without `X-Mock-User-Id` return
  `403 API token cannot access endpoint: <path>`;
- `X-Mock-User-Id` keeps precedence over bearer tokens for local development;
- existing super-admin label definition behavior is unchanged.

Out of scope:

- global middleware for every route;
- non-label admin routes;
- OAuth/session behavior;
- Java `server/` edits.

## Verification

- Add route tests covering bearer unsupported, invalid bearer, and mock-user precedence.
- Run targeted Python tests and Vite proxy tests.
- Run a manual hybrid live gate comparing Java, direct Python, and Vite proxy for at least one admin
  label route.


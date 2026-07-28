# Skill Collections Remediation Task 3 Result

Date: 2026-07-27

Task: Enforce the existing Web principal policy on new collection and
repository-import mutation routes.

## Scope and boundary

This task changes only the route-level principal resolver in:

- `server-python/app/api/collections.py`;
- `server-python/app/api/repository_imports.py`.

It adds focused authorization tests in:

- `server-python/tests/test_collection_access.py`;
- `server-python/tests/test_repository_import_api.py`.

It does not change collection/import services, repositories, persistence,
Skill lifecycle, publish behavior, read endpoints, CLI resolve, feature flags,
session handling, API-token scope definitions, or Task 4 membership contracts.

## Result

All six collection Web mutations and all four repository-import Web mutations
now follow the existing platform policy:

1. resolve mock/session/bearer identity with
   `resolve_current_user_or_401`;
2. reject any resolved `api_token` principal with
   `reject_api_token_principal_for_route`;
3. only then enter namespace authorization, writer, service, publish, or
   collection mutation work.

The rejection is:

```text
403 API token cannot access endpoint: {request.url.path}
```

The policy applies only to the new `/api/web` mutation handlers. Collection
list/detail and CLI collection resolve continue to use their existing read
identity path.

## Covered routes

| Method | Route |
| --- | --- |
| `POST` | `/api/web/namespaces/{namespace}/collections` |
| `POST` | `/api/web/collections/{namespace}/{collection}/draft` |
| `PUT` | `/api/web/collections/{namespace}/{collection}/draft` |
| `DELETE` | `/api/web/collections/{namespace}/{collection}/draft` |
| `POST` | `/api/web/collections/{namespace}/{collection}/publish` |
| `PUT` | `/api/web/collections/{namespace}/{collection}/status` |
| `POST` | `/api/web/namespaces/{namespace}/repository-imports/preview` |
| `POST` | `/api/web/repository-imports/{import_id}/ingest` |
| `POST` | `/api/web/repository-imports/{import_id}/check-updates` |
| `POST` | `/api/web/repository-imports/{import_id}/collection-draft` |

Each route is tested with a bearer principal whose provider is `api_token` and
whose only scope is `skill:read`. The tests assert the exact path-specific
`403` response and that no injected writer or publisher was called.

Invalid bearer tokens remain `401 error.auth.required`. Existing mock-user
success, MEMBER denial, and disabled-feature `404` cases remain covered by the
adjacent route/access test suites.

## TDD evidence

The first executable test attempt exposed a missing `pytest` import during
collection; that test-only error was corrected before evaluating behavior.

The valid RED run then proved all ten routes reached their writer:

```text
10 failed, 36 passed, 1 warning
```

Collection routes surfaced the injected sentinel as `500`; repository-import
routes translated it to their existing generic `400`. Both outcomes showed
that API-token rejection had not yet occurred.

After applying the existing principal-policy helper in both API modules:

```text
46 passed, 1 warning in 16.04s
```

## Core-regression verification

The focused authorization and adjacent core gate covered collection mutation
success, feature isolation, repository import, publish validation, hard
delete, bearer resolution, and route-policy enforcement:

```text
113 passed, 1 warning in 48.59s
```

The final complete Python backend regression passed:

```text
1080 passed, 2 warnings in 137.98s
```

The warnings are the existing Starlette `TestClient` deprecation and the
intentional duplicate ZIP-name archive fixture warning.

Focused `git diff --check` exited `0`. Ruff is not installed in the current
backend virtual environment, so no Ruff result is claimed.

## Review disposition

Independent specification review returned `SPEC COMPLIANT` and independently
reran a 70-test focused gate.

Independent code-quality/core-regression review returned `PASS` and
independently reran the 46-test principal-policy gate. It confirmed:

- feature-disable dependencies still return `404` before authentication;
- invalid bearer credentials still return `401`;
- valid API-token mutation attempts return `403` before side effects;
- mock/session precedence is unchanged;
- HTTP exceptions are not rewritten by import error translation;
- collection read and CLI resolve routes remain available to their existing
  principals.

No Important or Critical Task 3 finding remains.

No commit, stage, push, deployment, feature enablement, or real GitLab/Nexus
operation was performed.

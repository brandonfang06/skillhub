# Auth Method Catalog Migration Result

## Summary

Moved public auth catalog read routes to FastAPI:

- `GET /api/v1/auth/providers`
- `GET /api/v1/auth/methods`

The milestone did not move login, session bootstrap, local auth mutations, OAuth callbacks, or
bearer-token authentication.

## Route Ownership

| Route | Before | After |
| --- | --- | --- |
| `GET /api/v1/auth/providers` | java | python |
| `GET /api/v1/auth/methods` | java | python |

Still Java-owned:

- `POST /api/v1/auth/direct/login`
- `POST /api/v1/auth/session/bootstrap`
- `POST /api/v1/auth/local/register`
- `POST /api/v1/auth/local/login`
- `POST /api/v1/auth/local/change-password`
- `/oauth2/**`

## Java Parity Outcome

- OAuth providers are sorted by registration id.
- Provider display names use configured `client-name`, falling back to the id.
- OAuth authorization URLs use `/oauth2/authorization/{id}`.
- Safe relative `returnTo` values are preserved and URL-encoded with Java-compatible form encoding.
- Unsafe `returnTo` values, including absolute URLs and protocol-relative URLs, are ignored.
- Auth methods preserve Java order: local password first, sorted OAuth methods next.
- Direct local and session-bootstrap methods remain disabled by default.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_auth_method_catalog.py tests/test_hybrid_makefile.py -q
```

Result: `12 passed, 1 warning`.

```powershell
cd web
npx.cmd vitest run vite.config.test.ts
```

Result: `36 passed`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-auth-method-catalog-smoke
```

Result: passed. The live gate compared Java, direct Python, and Vite proxy behavior for:

- providers without `returnTo`;
- providers with safe `returnTo`;
- providers with unsafe `returnTo`;
- methods without `returnTo`;
- methods with safe `returnTo`;
- methods with unsafe `returnTo`.

The gate also confirmed direct login and session bootstrap remain Java security-bound through the
Vite proxy, and ran Playwright smoke: `6 passed`.

## Risks And Follow-Up

- Python currently mirrors Java's default OAuth registrations and env-driven GitLab display name.
  If production adds dynamic provider configuration beyond current Spring properties, Python config
  should be expanded before final Java decommission.
- Direct login and session bootstrap are still Java-owned because they establish first-party
  sessions and require a separate auth/session bridge plan.

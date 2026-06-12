# OAuth Proxy Boundary Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the last Vite Java proxy target, `/oauth2/**`, to Python so the local frontend no longer routes any request family to the Java backend.

**Architecture:** Python owns the OAuth authorization boundary route and returns deterministic boundary responses while full OAuth provider exchange, callback handling, and Spring Session replacement remain deferred. Vite points `/oauth2` to the Python backend and tests assert no proxy rule targets Java `8080`.

**Tech Stack:** FastAPI, pytest/TestClient, Vite/Vitest, SkillHub migration docs.

---

## Scope

- Move `GET /oauth2/authorization/{registrationId}` to Python.
- Preserve auth catalog URLs that already point users at `/oauth2/authorization/{registrationId}`.
- Return `501 error.auth.oauth.deferred` for configured providers because Python does not yet perform the external provider redirect, callback token exchange, identity binding, or session cookie creation.
- Return `404 error.auth.oauth.providerNotFound` for unknown providers.
- Route `/oauth2/**` through Vite to Python and assert there are no remaining Java `8080` proxy targets.
- Do not edit Java `server/` source. Java files may be read only for contract discovery.

## Files

- Modify: `server-python/app/api/auth.py` for the Python OAuth authorization boundary route.
- Test: `server-python/tests/test_oauth_boundary.py` for known/unknown provider behavior.
- Modify: `web/vite.config.ts` to point `/oauth2` at Python.
- Test: `web/vite.config.test.ts` to remove Java OAuth expectations and assert no `8080` proxy targets remain.
- Modify: `docs/backend-python-migration/route-registry.md`.
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`.
- Create: `docs/backend-python-migration/results/2026-06-12-oauth-proxy-boundary-cutover.md`.

## Tasks

- [x] Write failing Python OAuth boundary tests:
  - `uv run pytest tests/test_oauth_boundary.py -q`
  - Expected before implementation: 404 for the missing route instead of the target `501`/`404` detail contract.
- [x] Write failing Vite proxy tests:
  - `npm.cmd run test -- vite.config.test.ts`
  - Expected before implementation: `/oauth2` still targets `http://localhost:8080`.
- [x] Implement the minimal FastAPI route:
  - Known configured provider: `501` with `detail = "error.auth.oauth.deferred"`.
  - Unknown provider: `404` with `detail = "error.auth.oauth.providerNotFound"`.
- [x] Switch Vite `/oauth2` proxy target from `8080` to `8081`.
- [x] Update migration registry and sequence docs.
- [x] Verify:
  - `uv run pytest tests/test_oauth_boundary.py tests/test_auth_method_catalog.py tests/test_route_registry.py -q`
  - `npm.cmd run test -- vite.config.test.ts`
  - `rg -n "target:\s*'http://localhost:8080'|toBe\('http://localhost:8080'\)" web\vite.config.ts web\vite.config.test.ts` returns no matches.
  - Hybrid live gate proves Vite `/oauth2/authorization/github` matches Python direct behavior and no longer matches Java proxy routing.
- [ ] Review diff, record results, then commit and push the verified slice.

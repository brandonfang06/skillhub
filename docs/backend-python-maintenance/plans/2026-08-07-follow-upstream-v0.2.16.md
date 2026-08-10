# Upstream v0.2.16 Python-Only Follow-Up Plan

**Date:** 2026-08-10

## Goal

Port the applicable behavior from upstream SkillHub `v0.2.16` while preserving
the FastAPI backend and the existing root deployment. Sub-path support must
work both when Istio strips `/skillhub` and when the web image receives the
prefix unchanged.

## Release Evidence

- Release: <https://github.com/iflytek/skillhub/releases/tag/v0.2.16>
- Compare: <https://github.com/iflytek/skillhub/compare/v0.2.15...v0.2.16>
- Official scope: sub-path deployment, starter Skills, request/message
  correlation, optional tracing, label-index observability, label navigation,
  React 19 overlay fixes, CJK redirects, version-delete safety, and smoke-test
  credential isolation.
- The CLI remains `cli-v0.1.9`; no CLI version bump is part of this plan.

## Architecture Decision

Use a hybrid alignment rather than replacing the local implementation.

- Keep the local runtime-config, `buildAppPath()`, `toAppRelativePath()`,
  `buildReturnTo()`, explicit Python public URL/base-path configuration, and
  canonical `SKILLHUB_WEB_BASE_PATH=/skillhub` operator format.
- Adapt upstream's generated Nginx prefix router so the same web image handles
  root requests, requests already rewritten by Istio, and raw `/skillhub/...`
  requests.
- Add upstream's reserved-first-segment and same-origin API-base fail-fast
  checks to the release validator and image entrypoint.
- Do not adopt build-time base-path baking or mutate every compiled JS/CSS file
  at startup. The local runtime bundle is already path-independent.
- Do not use `X-Forwarded-Prefix` as a second source of truth. The Python
  backend continues to derive external URLs and cookie scope from its explicit
  configuration.

## Non-Negotiable Compatibility Matrix

| Mode | Browser URL | Request reaching web image | Required result |
| --- | --- | --- | --- |
| Root | `/dashboard`, `/assets/...`, `/api/...` | unchanged root path | Existing behavior remains byte/route compatible. |
| Existing organization topology | `/skillhub/...` | Istio rewrites to `/...` | Existing deployment continues to work without VirtualService changes. |
| Self-contained image topology | `/skillhub/...` | prefix remains intact | Nginx strips only configured prefix and redispatches to static/API/OAuth locations. |

The exact prefix `/skillhub` must redirect to `/skillhub/`. Root `/` must not
redirect. An empty or `/` base path must not generate a prefix location.

## Milestone 1: Sub-Path Image Hardening

**Files:**

- `web/docker-entrypoint.d/20-base-path-routing.sh`
- `web/docker-entrypoint.d/30-runtime-config.sh`
- `web/nginx.conf.template`
- `web/Dockerfile`
- `scripts/validate-release-config.sh`
- `server-python/tests/test_release_config_validation.py`
- `server-python/tests/test_deployment_cutover.py`
- `scripts/tests/web-base-path-nginx-smoke-test.sh`

Test-first requirements:

1. Reject base paths whose first segment is `api`, `oauth2`, `login`,
   `assets`, `registry`, `nginx-health`, `.well-known`, or
   `runtime-config.js` in release validation and container startup.
2. For a non-root base, allow a blank API base, the matching root-relative API
   base, or an absolute HTTP(S) API URL; reject other same-origin relative
   paths.
3. Generate no sub-path location for root deployment.
4. Generate an exact redirect and prefix rewrite for `/skillhub` deployment.
5. Run the real Nginx image and prove root and `/skillhub` assets return actual
   JavaScript rather than SPA HTML; prove SPA deep links, API proxying, OAuth
   callbacks, registry files, runtime config, health, uploads, and SSE remain
   correctly routed.

Success criteria: all three compatibility modes pass with one image, and the
current VirtualService rewrite remains supported.

## Milestone 2: Focused Frontend Reliability

Compare upstream `#624` and `#625` against the current React 19 code. Add
reproduction tests before changing shared overlays or label chips. Port only
confirmed gaps and use local base-path navigation helpers.

Success criteria: overlay open/unmount/navigation does not raise DOM teardown
errors; label chips navigate to the filtered search page at root and
`/skillhub`; narrow viewports do not overflow.

## Milestone 3: Backend Reliability Contracts

Compare upstream `#641`, `#674`, `#684`, and `#685` with FastAPI equivalents.

- Preserve the local archived rejected-review history and last-version
  invariant; never copy Java deletion semantics blindly.
- Percent-encode CJK redirect paths and reject response-header injection.
- Report committed label-index refresh failures through bounded logs and
  metrics without rolling back committed database state.
- Record Spring MVC-specific error mapping as a no-op unless a FastAPI 500 is
  reproducible.

Success criteria: focused tests use real PostgreSQL for lifecycle mutations
and verify actual FastAPI redirect/error responses.

## Milestone 4: Correlation And Optional Tracing

Reuse the existing request ID at selected Redis producer/consumer boundaries.
Define trusted carrier keys and reject malformed/unbounded values. Tracing is
optional, disabled by default, and must not require an external collector for
startup or request handling.

Success criteria: real Redis tests prove propagation and context cleanup;
root/sub-path behavior and scanner payload compatibility do not change.

## Milestone 5: Starter Skill Supply Chain

Treat upstream starter Skills as third-party content. Verify source commit,
license, notices, allowed files, deterministic package bytes, hashes, scanner
results, upgrade conflicts, retries, and PostgreSQL/MinIO compensation before
selecting any Skill. Non-selection is valid.

Success criteria: tampered or non-reproducible artifacts fail closed and no
existing built-in Skill is overwritten silently.

## Milestone 6: Final Verification And Review

Run focused tests after each milestone, then run:

```powershell
cd server-python
uv --no-cache run pytest tests -q
uv --no-cache run python -m app.migrations upgrade

cd ..\web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test
corepack pnpm run build

cd ..
docker build -t skillhub-web:v0216-verify -f web/Dockerfile web
docker build -t skillhub-server-python:v0216-verify -f server-python/Dockerfile .
docker compose --env-file .env.release.example -f compose.release.yml config --quiet
kubectl kustomize deploy\k8s\base
kubectl kustomize deploy\k8s\overlays\external
git diff --check
```

Run production-image browser scenarios at root and `/skillhub` on desktop and
mobile with PostgreSQL, Redis, MinIO, scanner, FastAPI, and web healthy. Review
the final diff for route shadowing, redirect loops, double-prefix generation,
cookie/OAuth regressions, proxy trust changes, lifecycle evidence loss,
post-commit side effects, and startup coupling.

## Explicit Non-Goals

- Do not reintroduce Java, Maven, Spring Boot, Redisson, Flyway, or the removed
  Java server tree.
- Do not require a VirtualService change for existing deployments.
- Do not remove the current Istio rewrite during the initial rollout.
- Do not add a database migration without a demonstrated Python contract gap.
- Do not make Helm, tracing infrastructure, or the entire upstream starter
  catalog mandatory.
- Do not modify, stage, commit, or remove unrelated dirty-worktree files.

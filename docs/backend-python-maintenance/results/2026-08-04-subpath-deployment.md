# Canonical Subpath Deployment Result

**Date:** 2026-08-04
**Branch:** `codex/subpath-deployment`
**Status:** Implementation and verification complete; not committed or merged

## Outcome

SkillHub now supports the canonical browser entrypoint
`https://ai-coding-platform.tsmc.com/skillhub` while keeping backend routes
root-relative behind an Istio prefix rewrite.

- `SKILLHUB_PUBLIC_BASE_URL` is the complete public application URL used by
  OAuth callbacks, browser links, device authorization, and session scope.
- `SKILLHUB_WEB_BASE_PATH=/skillhub` configures router, assets, lazy chunks,
  redirects, SSE, downloads, and same-origin API calls.
- A blank `SKILLHUB_WEB_API_BASE_URL` inherits the browser base path.
- `SKILLHUB_WEB_CLI_REGISTRY_URL` remains an independent frontend-only
  override for copied CLI commands.
- Session cookies use `/skillhub`; production operators must keep
  `SKILLHUB_SESSION_COOKIE_SECURE=true` at the HTTPS entrypoint.
- Root deployments retain their existing empty base path and `/` cookie path.

The deployment manual includes the CNAME/SNI/HTTP Host boundary, a safe
additive Gateway server patch fragment, the Istio exact/prefix match and
internal rewrite, certificate Secret ownership, and the required Keycloak Root
URL, Home URL, exact redirect URI, and origin-only Web Origins value. DNS,
certificate, and Gateway configuration use only the hostname, never
`/skillhub`.

## Review Findings Fixed

The review used browser and container scenarios in addition to unit tests and
found fifteen issues not adequately covered by the initial test set.

1. Browser `setTimeout` and `clearTimeout` methods were passed unbound to the
   notification SSE coordinator. Chrome raised `Illegal invocation` while
   reconnecting. The default timer adapter now calls the global methods with
   their correct receiver.
2. Component-level role guards kept `/skillhub` inside `returnTo`. The backend
   correctly rejected the already-prefixed path to prevent duplication, but
   users then returned to the default dashboard after login. The shared login
   redirect now converts the browser URL to an app-relative path first.
3. Public URL validation accepted whitespace or percent escapes in the
   hostname, and encoded return paths could hide an already-present public
   prefix. The backend now rejects malformed netloc values and compares the
   decoded return pathname before constructing redirects.
4. Release validation did not inspect `SKILLHUB_WEB_BASE_PATH`, did not reject
   a public/base path mismatch, and validated the legacy device URL even when
   the canonical override won. Twenty real shell scenarios now cover valid,
   malformed, mismatch, canonical/legacy precedence, and derived defaults.
5. Kubernetes can bypass the release script. Backend startup now independently
   rejects relative, non-HTTP, credential-bearing, query-bearing, and
   fragment-bearing explicit device verification URLs.
6. The first shared URL refactor removed an explicit device URL trailing slash,
   and frontend normalization accepted characters or repeated slashes rejected
   by the container. Explicit URLs are now preserved while frontend,
   entrypoint, and release-validator base-path contracts agree.
7. A complete-looking Gateway example containing only the new listener could
   overwrite organization-managed servers if applied directly. Documentation
   now provides a clearly labelled additive patch fragment and keeps the old
   `skillhub-test.ftest.tsmc.com` server/VirtualService separate.
8. The production image assigned the runtime base href and several default
   runtime flags as unexported shell variables. `envsubst` therefore generated
   an empty `<base href>` and blank defaults even though unit and proxy E2E
   tests passed. The entrypoint now explicitly exports every runtime template
   variable, and a real image/container check verifies the generated files.
9. Release URL validation accepted malformed authorities, invalid ports, path
   traversal segments, and percent escapes that backend startup could reject.
   The shell validator and backend URL contract now agree on these boundaries.
10. Kubernetes could supply a public URL path that disagreed with the frontend
    base path, and an HTTPS deployment could start with an insecure session
    cookie. The backend now receives the web base path and rejects both unsafe
    combinations during startup.
11. Runtime values containing quotes, backslashes, or control characters could
    produce invalid or injected JavaScript while the Nginx health check stayed
    green. The image entrypoint now rejects unsafe template values before
    writing generated files.
12. Browser coverage exercised only three flows. The production-build suite now
    covers landing, dashboard, SSE, lazy chunk reload, authenticated download
    and logout, anonymous OAuth initiation, OAuth callback, CLI authentication,
    and CSV export under both desktop and mobile viewports.
13. Backend startup initially checked only the canonical secure-cookie variable
    while the cookie implementation also accepted the legacy name, and their
    handling of whitespace-only values differed. Both paths now share the same
    precedence and boolean parser.
14. Release preflight treated an insecure, blank, or omitted session-cookie
    setting as a warning/default even when the public URL was HTTPS, while the
    backend refused to start. These combinations now fail before deployment.
15. Shell and backend authority validation differed for quoted hostnames and
    bracketed IPv6 literals. Valid IPv6, optional ports, compression, hextet
    counts, and IPv4 tails now have matching positive and negative coverage.

No unresolved correctness or security finding remains in the reviewed scope.
No database schema, skill lifecycle, visibility, review, scanner, or CLI
business behavior changed.

## Verification

Passed:

```text
Backend: 1126 passed, 1 existing Starlette/httpx deprecation warning
Frontend: 198 test files, 760 tests passed
Frontend typecheck, ESLint, and production build
Python application compileall
Production subpath Playwright: 14 passed across desktop and mobile projects
Docker web and Python backend image builds
Live root and subpath Nginx container runtime and zero-mount verification
Docker workspace audit: 25 containers, 17 mounts, 0 legacy OneDrive mounts
kubectl kustomize deploy\k8s\base: 634 rendered lines
docker compose --env-file .env.release.example -f compose.release.yml config --quiet
Release-validator and web-entrypoint shell syntax; root/subpath base-template generation
git diff --check
```

The Playwright suite uses the fresh production bundle behind a prefix-stripping
proxy. It verifies landing and dashboard navigation, SSE, lazy review-detail
chunk loading and reload, authenticated download/logout traffic, anonymous
login, OAuth initiation and callback, CLI authentication, CSV export, and no
horizontal overflow at `390x844` and `1440x900`.

The production build retains the existing runtime-config resolution,
Browserslist freshness, and large-chunk warnings. Vitest retains an existing
jsdom navigation message. Compose configuration succeeds with local Docker
config permission warnings.

The Docker runtime check built `skillhub-web-subpath:verify` and
`skillhub-server-python:verify`. It started the real Nginx image as both a root
deployment and the canonical `/skillhub` deployment, reached healthy status,
verified zero host mounts and the generated base tag/runtime config/registry
document inside each container, resolved and fetched browser assets, and
confirmed an invalid `//evil` base path exits with the expected fail-fast error.
The separate workspace audit inspected every local Docker container and found
no mount source under `C:\Users\USER\OneDrive\Documents\skillhub`; the two
SkillHub bind mounts found resolve under `C:\Users\USER\projects\skillhub`.

The original review run did not include Ruff or ShellCheck. The follow-up run
installed both tools and records their scoped results below.

## 2026-08-05 Review Follow-up

A post-merge scenario review found and fixed seven additional gaps:

1. Subpath login and logout now expire the legacy root `SESSION` cookie, prefer
   the first valid path-ordered session, invalidate every duplicate session id
   during logout, and rotate all request-provided sessions on login.
2. `runtime.sh --public-url` now derives and persists
   `SKILLHUB_WEB_BASE_PATH`, including normalization of a trailing slash.
3. The subpath Playwright global setup now builds the current TypeScript/Vite
   production bundle before importing the server that reads `dist`.
4. Backend and shell release URL validation now reject port zero, empty DNS
   labels, and labels with leading or trailing hyphens while retaining internal
   single-label and IPv6 support.
5. The ClawHub well-known agent and user documentation now describes both root
   and configured subpath API bases.
6. The backend image used `uv run` after building with `uv sync --no-dev`, so
   container startup could contact the package registry and install dev
   dependencies. Runtime now invokes the bundled virtual environment directly
   and uses `exec` for the final Uvicorn process.
7. The runtime imports `httpx` for OAuth and scanner calls, but `httpx` was
   declared only in the dev dependency group. It is now a production
   dependency, so the no-dev image imports the complete FastAPI application.

Fresh follow-up verification passed: `1184` backend tests, `786` frontend
tests, typecheck, ESLint, two shell syntax checks, `117` focused deployment
tests, `16` production subpath Playwright tests, Kustomize rendering, Compose
configuration, both production Docker image builds, and `git diff --check`.

The final backend image also loaded the complete application and canonical URL
settings with Docker networking disabled, proving startup imports do not need a
runtime package download. The frontend image served its generated base tag,
runtime config, real hashed JavaScript asset, and health endpoint using the
documented VirtualService prefix-rewrite model. Scoped Ruff and ShellCheck
checks passed after the tools were installed.

## 2026-08-07 Session Safety Follow-up

A second post-merge review reproduced four session and validation risks that
were not covered by the original happy-path tests:

1. A subpath response could delete another same-host application's root
   `SESSION` cookie. Root-cookie cleanup now requires exactly two raw,
   path-ordered cookie slots and occurs only when the root candidate resolves
   to a live SkillHub session. Three or more slots remain ambiguous and never
   trigger root-cookie deletion.
2. An untrusted request could provide an arbitrary number of duplicate
   `SESSION` values and amplify one request into many sequential Redis calls.
   Authentication reads at most the expected scoped/root pair. Login and
   logout revoke at most three candidates in one bounded operation so an
   ambiguous live root session cannot survive, and oversized ids never reach
   Redis. A fourth candidate is rejected with a `400` before any session
   mutation, registration, credential check, OAuth exchange, or identity
   binding instead of reporting a successful login or logout.
3. Login created a new Redis session before deleting old sessions, so a
   partial failure could leave mixed state. Redis rotation now uses one
   transactional pipeline, and logout uses one multi-key delete.
4. Shell validation counted a trailing DNS root dot before applying the
   253-character hostname limit while backend validation counted it after
   normalization. Both now apply the limit to the normalized hostname.

The follow-up passed `1205` backend tests with one environment-gated
PostgreSQL test skipped, `138` focused
auth/session/OAuth/release-validator tests, Ruff, ShellCheck, shell syntax,
Kustomize rendering, Compose configuration, and `18` desktop/mobile production
subpath Playwright tests. A real Redis 7 container verified transactional
rotation, TTL retention, and multi-key deletion. The production backend image
built successfully and loaded the complete app with networking disabled.

## Remaining Organization Runtime Gates

The organization-only CNAME, certificate chain/trust, Gateway credential
namespace, TLS SNI, HTTP Host routing, Keycloak client, and authenticated
canonical-URL browser flow cannot be reached from this development network.
They remain explicit go/no-go gates in
`docs/backend-python-maintenance/plans/2026-08-04-canonical-subpath-rollout-checklist.md`.

No deployment or external organization configuration change was performed.

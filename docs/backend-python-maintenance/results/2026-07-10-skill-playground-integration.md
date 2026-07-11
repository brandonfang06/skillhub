# Skill Playground Sidecar Integration Result

Date: 2026-07-10
Final verification: 2026-07-11

## Outcome

SkillHub now has a disabled-by-default entry point for a separately deployed,
prompt-only skill playground. The reusable runtime lives in the independent
private repository `brandonfang06/skill-playground-sidecar`.

SkillHub owns only:

- short-lived `playground:read` capability issuance;
- bounded, read-only skill context retrieval through existing access readers;
- web runtime flags, a skill-detail action, and a dedicated route;
- a direct browser-to-sidecar session/SSE client.

The sidecar owns configuration, allowlisted context providers, in-memory
sessions, prompt construction, OpenAI-compatible model streaming, CORS, health,
and its container image. It has no SkillHub database, Redis, object-store,
worker, startup, readiness, or lifecycle dependency.

## Failure Isolation

- Empty `SKILLHUB_PLAYGROUND_TOKEN_SECRET` leaves the backend running and makes
  only capability creation unavailable.
- Empty or disabled web runtime settings hide the detail-page entry point.
- Sidecar connection/provider errors remain local to the dedicated route.
- SkillHub never calls or probes the sidecar during startup, health, search,
  detail, download, install, publish, or review.
- Context reads reuse version/detail/file readers and never call download
  readers or mutate download metrics.
- Context fallback tests verify access is re-evaluated after capability
  issuance, so later permission revocation is enforced.
- SkillHub base K8s manifests contain no playground workload or probe.
- The web client keeps generation busy until the SSE completion event and
  treats provider/input/message-limit errors as local, resettable session
  errors instead of a SkillHub outage.

The repeatable isolation gate is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-playground-isolation.ps1
```

Result: backend `84 passed`, frontend `52 passed`, and frontend typecheck passed
with all playground settings disabled and no sidecar process required.

## Verification

```text
sidecar: uv run pytest tests -q
19 passed

SkillHub backend: uv run pytest tests -q
906 passed, 1 pre-existing Starlette TestClient deprecation warning

SkillHub web: corepack pnpm test
191 test files passed, 643 tests passed

SkillHub web: corepack pnpm run typecheck
passed

SkillHub web: corepack pnpm run lint
passed

SkillHub web: corepack pnpm run build
passed; existing runtime-config and chunk-size warnings remain

kubectl kustomize deploy\k8s\base
passed; rendered output contains no playground workload

docker compose --env-file .env.release.example -f compose.release.yml config
passed

git diff --check
passed in both repositories
```

A live browser test used the actual SkillHub React route, actual sidecar, an
allowlisted SkillHub-compatible context endpoint, and an OpenAI-compatible SSE
provider. It verified session creation, two read-only context files, prompt
submission, and a streamed assistant response. At 390px width, the context and
chat regions stacked vertically and document width matched viewport width.

Docker image build was not run because the local Docker Desktop daemon was not
available. The Dockerfile is present and sidecar application startup was
verified directly with its production Uvicorn factory command.

## OpenAPI Note

`web/src/api/generated/schema.d.ts` was not regenerated or manually edited.
The current Python OpenAPI document still omits existing Java-era components
used by the frontend, including `AuthMeResponse`; full regeneration therefore
breaks unrelated existing types. The playground capability uses the repository's
transitional hand-written type pattern until the broader OpenAPI sync gap is
resolved.

## Removal

1. Set `SKILLHUB_WEB_PLAYGROUND_ENABLED=false` and clear the sidecar base URL.
2. Remove the independently deployed sidecar.
3. Optionally clear `SKILLHUB_PLAYGROUND_TOKEN_SECRET` in the backend.

No schema, shared infrastructure, or data cleanup is required.

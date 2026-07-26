---
name: testing-and-ci
description: Testing conventions, CI gates, and smoke coverage for the SkillHub Python backend, frontend, scanner, and CLI.
license: Apache-2.0
---

# Testing And CI Skill

## Trigger

Use this skill when adding tests, changing CI, modifying operator workflows, or
preparing release verification.

## Backend Testing

Backend tests live in `server-python/tests/` and use pytest.

```powershell
cd server-python
uv run pytest tests -q
```

Testing requirements:

- Route changes: request, response envelope, status, and request-id behavior.
- Protected routes: session, role, API-token, and authorization behavior.
- Writes: idempotency, transaction, audit actor, and rollback or compensation.
- Integrations: storage, scanner, Redis, notification, and external HTTP
  failure behavior when touched.
- Schema changes: migration and transaction tests.

Use focused tests while iterating, then run the complete backend suite before
claiming completion.

## Frontend And CLI

```powershell
cd web
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run test:e2e:smoke

cd ..\cli
bun run typecheck
bun run lint
bun test
bun run build
```

Frontend unit tests use Vitest. Authenticated browser and viewport flows use
Playwright. CLI unit and integration tests use Bun.

## Smoke Tests

| Script | Purpose |
| --- | --- |
| `scripts/smoke-test.sh` | Health, metrics, auth, and labels |
| `scripts/namespace-smoke-test.sh` | Namespace membership and publishing |
| `scripts/governance-smoke-test.sh` | Governance and moderation |
| `scripts/promotion-smoke-test.sh` | Skill promotion |
| `scripts/publish-scan-download-smoke-test.sh` | Scanner publish workflow |
| `scripts/cli-staging-smoke-test.sh` | CLI registry workflow |

When an operator-facing workflow changes, update and run the corresponding
smoke test.

## Deployment Verification

For backend, scanner, or deployment changes:

```powershell
docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
```

## Pre-PR Checklist

- Relevant focused tests pass.
- Full backend tests pass for backend changes.
- Frontend typecheck and lint pass for frontend changes.
- CLI typecheck, lint, tests, and build pass for CLI changes.
- OpenAPI types are regenerated after API contract changes.
- Deployment artifacts render after deployment changes.
- `git diff --check` passes.

# server-python AGENTS.md

This directory contains the FastAPI backend that replaces the Java `server/`
backend before SkillHub goes live for the organization.

The project is still pre-launch. That means migration does not need to optimize
for a long production coexistence window. Prefer faster, coherent Python
ownership when it is easier to verify and maintain, while still using Java as a
read-only contract reference until Python has taken over the relevant surface.

## Mission

- Make `server-python/` the future primary backend for internal organizational
  use.
- Use Java `server/` as a read-only reference implementation, not as a backend
  that must remain production-compatible forever.
- Preserve external contracts that the frontend, CLI compatibility layer, and
  tests rely on unless a written migration plan explicitly changes the contract.
- During migration, Java may still run on `localhost:8080` and Python on
  `localhost:8081` for comparison, but long-term dual-backend operation is not
  the goal.

## Pre-Launch Migration Strategy

Because the service is not live yet, agents may migrate more boldly than the
original one-route-at-a-time coexistence strategy.

Preferred approach:

- Migrate by cohesive API area or workflow when that reduces duplicated
  Java/Python boundary work.
- It is acceptable for Python to take ownership of a broader route group once
  tests and live verification cover the group.
- Prefer finishing a full Python-owned vertical slice over preserving many
  tiny Java/Python splits that create proxy complexity.
- When a frontend workflow can be made to use Python consistently, prefer that
  over keeping adjacent reads split across Java and Python.
- Keep Java available as a comparison oracle until the migrated group has
  passing tests and documented results.

Still required:

- Announce the planned migration scope before implementation.
- Write/update a plan before code changes.
- Run Python tests, Vite proxy tests when relevant, and live Java/Python
  comparison while Java reference behavior is still useful.
- Record result documents before commit/push.
- Keep `server/` strictly read-only.

## Documentation Index

Use this file as the entrypoint for Python backend migration sessions. There is
currently no root `CLAUDE.md`; keep the migration-specific index here so a new
session can find the rest of the repo documentation without searching.

### Agent And Workflow Entrypoints

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Root project agent rules, architecture map, coding conventions, PR checklist, and SkillHub domain overview. |
| `server-python/AGENTS.md` | Python migration-specific rules, Java read-only boundary, route ownership workflow, and this documentation index. |
| `SDLC-README.md` | Chinese SDLC guide for team members, including Windows/macOS/Ubuntu environment rules and Python migration expectations. |
| `README.md` / `README_zh.md` | Product overview and baseline setup documentation. |
| `CONTRIBUTING.md` | Contribution and PR workflow. |

### Backend Python Migration Source Of Truth

| Path | Purpose |
| --- | --- |
| `docs/backend-python-migration/00-governance.md` | Migration governance, non-negotiable boundaries, and session rules. |
| `docs/backend-python-migration/migration-sequence-plan.md` | Living migration order. Update this before changing API priorities. |
| `docs/backend-python-migration/java-parity-checklist.md` | Required Java parity checklist for every migration milestone plan/result. |
| `docs/backend-python-migration/route-registry.md` | Human-readable Java/Python route ownership registry. Keep in sync with Vite proxy. |
| `docs/backend-python-migration/hybrid-local-e2e.md` | Cross-platform Java/Python/Vite local E2E workflow. |
| `docs/backend-python-migration/windows-live-verification.md` | Windows-specific Docker Desktop, Codex sandbox, and live verification notes. |
| `docs/backend-python-migration/plans/` | Per-milestone implementation plans. Create/update before coding a milestone. |
| `docs/backend-python-migration/results/` | Per-milestone verification results. Write before commit/push. |

Current completed migration result examples:

- `docs/backend-python-migration/results/2026-06-07-public-labels-live-verification.md`
- `docs/backend-python-migration/results/2026-06-07-skill-labels-list-api.md`

### Core Product And Architecture Docs

| Path | Purpose |
| --- | --- |
| `docs/00-product-direction.md` | Product positioning, MVP scope, and coordinate model. |
| `docs/01-system-architecture.md` | System architecture and module boundaries. |
| `docs/02-domain-model.md` | Domain entities and relationships. |
| `docs/03-authentication-design.md` | OAuth2, local auth, CLI auth, and token model. |
| `docs/04-search-architecture.md` | Search SPI and PostgreSQL search design. |
| `docs/05-business-flows.md` | Main business workflows. |
| `docs/06-api-design.md` | REST API design reference. |
| `docs/07-skill-protocol.md` | `SKILL.md` package protocol. |
| `docs/08-frontend-architecture.md` | Frontend architecture and conventions. |
| `docs/09-deployment.md` | Deployment design. |
| `docs/10-delivery-roadmap.md` | Delivery roadmap. |
| `docs/14-skill-lifecycle.md` | Authoritative skill lifecycle model. |
| `docs/2026-03-20-skill-label-system-design.md` | Skill label system design; relevant for label-related migrations. |

### Additional Design And Operations Docs

| Path | Purpose |
| --- | --- |
| `docs/11-auth-extensibility-and-private-sso.md` | Auth extensibility and private SSO design. |
| `docs/12-private-sso-integration-playbook.md` | Private SSO integration playbook. |
| `docs/15-backend-time-governance-plan.md` | Backend time handling governance plan. |
| `docs/16-backend-time-inventory.md` | Backend time usage inventory. |
| `docs/17-backend-annotation-findings.md` | Backend annotation findings. |
| `docs/18-frontend-annotation-findings.md` | Frontend annotation findings. |
| `docs/19-smtp-password-reset-email-setup.md` | SMTP password reset setup. |
| `docs/openclaw-integration.md` / `docs/openclaw-integration-en.md` | OpenClaw integration notes. |
| `docs/oss-01-core-contract-freeze.md` | OSS core contract freeze notes. |
| `docs/oss-02-core-semantic-rules.md` | OSS semantic rules. |
| `docs/pr-batch-test-runtime.md` | PR batch test runtime notes. |
| `docs/security-scanning.md` | Security scanning design and usage notes. |

### Planning, PRDs, And Historical Work

| Path | Purpose |
| --- | --- |
| `docs/prds/` | Product requirement documents and acceptance/test plans. |
| `docs/superpowers/specs/` | Historical design specs produced by planning sessions. |
| `docs/superpowers/plans/` | Historical implementation plans. |
| `docs/13-parallel-workflow.md` | Parallel agent/worktree workflow. |
| `docs/dev-workflow.md` | Local development workflow guide. |
| `docs/e2e.md` | E2E testing notes. |

### User-Facing And Generated Documentation

| Path | Purpose |
| --- | --- |
| `docs/skillhub/` | VitePress-style user guide source in Chinese and English. |
| `document/docs/` | Docusaurus/VitePress published documentation content. |
| `document/i18n/` | English localized documentation mirror. |
| `web/src/docs/` | In-app frontend documentation content. |

### Component-Specific Docs

| Path | Purpose |
| --- | --- |
| `server-python/README.md` | FastAPI backend local notes. |
| `scanner/README.md` and `scanner/docs/` | Security scanner setup, rules, monitoring, and configuration. |
| `cli/README.md` and `cli/RELEASE.md` | CLI usage and release notes. |
| `deploy/k8s/README.md` | Kubernetes deployment notes. |
| `web/LANDING_PAGE_REDESIGN.md`, `web/PREVIEW.md`, `web/TODO.md` | Frontend-specific design and work notes. |

### How To Add New Docs

- Migration design or implementation discussion goes under
  `docs/backend-python-migration/` when it affects Java -> Python coexistence.
- Milestone plans go under `docs/backend-python-migration/plans/`.
- Milestone outcomes go under `docs/backend-python-migration/results/`.
- Product requirements go under `docs/prds/`.
- Broad architecture updates go under numbered files in `docs/`.
- If a new documentation area is added, update this `Documentation Index` in
  the same commit.

## Absolute Java Boundary

- Never edit, move, delete, format, or regenerate any file under `server/`.
- Treat `server/` as read-only reference implementation.
- You may read Java code, run Java tests, and start the Java server for
  comparison.
- You may not change Java controllers, services, domain models, repositories,
  configs, tests, Maven files, Dockerfiles, scripts, or Flyway migrations.
- If a migration appears to require Java changes, stop and document the blocker
  in the session result. Do not work around it by editing Java.

## Hard Boundaries

- Do not migrate an endpoint or route group unless it is listed or planned in
  `docs/backend-python-migration/route-registry.md` and a milestone plan.
- Database schema ownership has moved to the Python migration command for the
  final cutover path. Keep Java Flyway files under `server/` read-only, and add
  future schema changes through explicit `server-python` migration plans.
- Do not implement auth/session/OAuth/API-token behavior unless a written
  migration plan explicitly covers it.
- Mutating endpoints may be migrated before production only when their
  idempotency, authorization assumptions, and rollback behavior are written in
  the plan and covered by tests.
- Do not edit generated frontend API types manually.

## Python Tooling

- Use Python 3.12.
- Use `uv` for dependency and virtual environment management.
- Virtual env path: `server-python/.venv`.
- Commit `pyproject.toml` and `uv.lock`.
- Never commit `.venv`.

Common commands:

```powershell
cd server-python
uv venv .venv
uv sync
uv run pytest
uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

Dependency changes must use:

```powershell
uv add <package>
uv remove <package>
```

Record every dependency change in the session result document.

## API Contract Rules

- SkillHub web/API responses must use the SkillHub envelope:

```json
{
  "code": 0,
  "msg": "success",
  "data": {},
  "timestamp": "2026-06-06T00:00:00Z",
  "requestId": "..."
}
```

- ClawHub compatibility routes intentionally return plain ClawHub JSON. Do not
  wrap those routes in the SkillHub envelope.
- Reuse incoming `X-Request-Id`; generate one when missing.
- Return `X-Request-Id` in response headers.
- Preserve Java status codes, response shapes, pagination fields, and
  file/download exceptions.
- Do not introduce Python-only response formats.

## Route Ownership

Every endpoint migration must update:

- `docs/backend-python-migration/route-registry.md`
- `web/vite.config.ts`
- the related session plan under `docs/backend-python-migration/plans/`
- the related session result under `docs/backend-python-migration/results/`

A route must have exactly one active owner: `java` or `python`.

Pre-launch route ownership may move in larger groups. If a group migration
changes many routes at once, update the registry as a group and include a
verification matrix in the result document.

## Architecture

Prefer small modules with clear boundaries:

- `app/main.py`: FastAPI app factory and router registration
- `app/api/`: route handlers
- `app/core/`: config, request id middleware, response envelope helpers
- `app/db/`: SQLAlchemy engine/session setup
- `app/repositories/`: database queries
- `app/services/`: business workflow orchestration
- `app/schemas/`: Pydantic request/response models
- `tests/`: pytest tests

Route handlers should stay thin: bind request data, call services, return
envelope responses.

### Data Access During Migration

The Java backend uses JPA/domain services/repositories. Python currently uses
SQLAlchemy async engine with explicit SQL (`sqlalchemy.text`) for migrated
catalog, file metadata, file content, and download read paths.

This is intentional migration bridge code:

- Preserve Java contract parity before redesigning internals.
- Keep query behavior narrow and easy to compare in live gates.
- Do not introduce SQLAlchemy ORM models for read/download migrations unless a
  milestone plan explicitly says to do so.
- Keep SQL in repository/helper functions, not route handlers.
- Revisit ORM/domain modeling before publish/upload/lifecycle mutations, where
  transaction boundaries, authorization, idempotency, and rollback behavior are
  higher risk.

### Java Parity Checklist

Every migration milestone must use
`docs/backend-python-migration/java-parity-checklist.md` before implementation
and again in the result document.

Minimum parity evidence:

- Java controller/service/repository/domain reference files inspected.
- API contract and error shape compared.
- authorization/session behavior classified as covered, not applicable, or
  deferred.
- transaction boundary and rollback/compensation behavior documented.
- audit actor fields such as `created_by`, `updated_by`, `submitted_by`, and
  `actor_user_id` verified when the milestone writes data.
- storage, scanner, event, and audit side effects verified or explicitly
  deferred.

Route ownership must not move while Java parity checklist items are unresolved
for that route. If a reviewer raises parity feedback, triage it as must-fix,
defer, or needs-evidence, then add tests for accepted fixes.

## Testing Requirements

Every change needs tests before or alongside implementation.

Minimum checks per migrated endpoint or route group:

- Python route test with `pytest`
- response envelope test
- request id propagation test
- contract comparison against Java behavior while Java remains a useful
  reference
- Vite proxy ownership test or config assertion when route ownership changes
- Java parity checklist guard for behavior touched by the milestone, including
  transaction boundary and audit actor coverage for mutations

Before marking a session complete, run:

```powershell
cd server-python
uv run pytest
```

If frontend proxy changed, also run the relevant web test/typecheck command from
`web/`.

## Session Documentation

Before implementation, write a plan in:

```text
docs/backend-python-migration/plans/YYYY-MM-DD-<topic>.md
```

After implementation, write a result in:

```text
docs/backend-python-migration/results/YYYY-MM-DD-<topic>.md
```

Each result must include:

- routes changed
- owner before/after
- Java parity checklist outcome
- files changed
- tests run and exact outcome
- known risks
- follow-up work

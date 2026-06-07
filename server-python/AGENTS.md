# server-python AGENTS.md

This directory contains the FastAPI backend that gradually replaces selected
Java `server/` endpoints during the Java/Python coexistence period.

## Mission

- Implement Python-owned API routes with the same external contract as the
  existing Java backend.
- Keep Java `server/` and Python `server-python/` running side by side during
  migration.
- Preserve frontend behavior: migrated routes go to `localhost:8081`;
  non-migrated routes stay on Java `localhost:8080`.

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

- Do not migrate an endpoint unless it is listed in
  `docs/backend-python-migration/route-registry.md`.
- Do not change database schema from Python during coexistence. Java Flyway
  remains the schema owner.
- Do not implement auth/session/OAuth/API-token behavior unless a written
  migration plan explicitly covers it.
- Do not migrate mutating endpoints until Python has equivalent `X-Request-Id`
  idempotency behavior.
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

- JSON responses must use the SkillHub envelope:

```json
{
  "code": 0,
  "msg": "success",
  "data": {},
  "timestamp": "2026-06-06T00:00:00Z",
  "requestId": "..."
}
```

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

## Testing Requirements

Every change needs tests before or alongside implementation.

Minimum checks per migrated endpoint:

- Python route test with `pytest`
- response envelope test
- request id propagation test
- contract comparison against Java behavior when practical
- Vite proxy ownership test or config assertion when route ownership changes

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
- files changed
- tests run and exact outcome
- known risks
- follow-up work

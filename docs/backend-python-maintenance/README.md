# Backend Python Maintenance

This directory tracks post-cutover backend hardening work after the Java-to-Python
runtime migration.

The migration baseline is the annotated tag `backend-python-cutover-2026-06-12`.
Work in this directory is not route ownership migration work. It is maintainability
work for the Python backend now that Python owns the default local, staging, and
API runtime paths.

## Rules

- Keep public API contracts stable unless a milestone explicitly fixes a bug.
- Keep Java `server/` read-only reference material.
- Move SQL toward repository/query/helper boundaries before introducing ORM.
- Introduce SQLAlchemy ORM only through a written milestone plan with targeted
  transaction tests.
- Preserve explicit SQL for projection-heavy reads when it is clearer, isolated,
  and covered by tests.

## Current Plan

- `docs/backend-python-maintenance/post-python-cutover-hardening-plan.md`

## Results

Milestone result notes live under `docs/backend-python-maintenance/results/`.
